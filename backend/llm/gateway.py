"""
LLMGateway (technical plan X-4, mục 5.3, quy tắc R3): mọi lời gọi LLM đi qua đây.

- Hội thoại nhiều lượt: messages = [{'role': system|user|assistant, 'content': ...}].
- Đầu ra có cấu trúc: truyền JSON schema (Ollama `format`), kiểm tra ở tầng dịch vụ.
- Streaming, giới hạn thời gian, model dự phòng.
- Hàng đợi ƯU TIÊN + giới hạn số yêu cầu song song (khớp OLLAMA_NUM_PARALLEL).
"""

import heapq
import itertools
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

import requests

from config import normalize_ollama_base_url
from provider.prompts import ThinkFilter, clean_response

# Mức ưu tiên (số nhỏ = ưu tiên cao)
PRIORITY_TRIAGE = 1        # AG-0
PRIORITY_INTERACTIVE = 2   # AG-1 (khách đang chờ), AG-6
PRIORITY_COPILOT = 3       # AG-2..4
PRIORITY_MANAGER = 4       # AG-7
PRIORITY_BACKGROUND = 5    # AG-5


class LLMError(RuntimeError):
    pass


class LLMTimeout(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    duration_s: float = 0.0
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    used_fallback: bool = False
    queue_wait_s: float = 0.0


@dataclass
class StreamStats:
    """Điền dần khi stream kết thúc (để dịch vụ ghi AiRun)."""

    provider: str = ''
    model: str = ''
    duration_s: float = 0.0
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    used_fallback: bool = False
    queue_wait_s: float = 0.0
    extra: dict = field(default_factory=dict)


# ============================================================
# Hàng đợi ưu tiên
# ============================================================

class PriorityLimiter:
    """
    Tối đa `max_parallel` yêu cầu chạy cùng lúc; ai chờ được phục vụ theo ưu tiên rồi FIFO.

    Giữ chỗ cho việc gấp: việc nền (ưu tiên >= PRIORITY_COPILOT: gợi ý, quản lý, hồ sơ ca)
    chỉ được dùng tối đa `max_parallel - reserved` chỗ, để kiểm tra trước khi gửi / trả lời
    khách / phân loại không phải xếp sau một gợi ý dài 60 s. Chỉ có tác dụng khi
    max_parallel >= 2 (Ollama đặt OLLAMA_NUM_PARALLEL >= 2); với 1 chỗ thì việc nền vẫn chạy.
    """

    def __init__(self, max_parallel=2, reserved=1):
        self.max_parallel = max_parallel
        self.reserved = reserved
        self._running = 0
        self._running_low = 0
        self._waiting = []
        self._counter = itertools.count()
        self._cond = threading.Condition()

    def set_max_parallel(self, value):
        with self._cond:
            self.max_parallel = max(1, int(value))
            self._cond.notify_all()

    def set_reserved(self, value):
        with self._cond:
            self.reserved = max(0, int(value))
            self._cond.notify_all()

    @staticmethod
    def _is_low(priority):
        return priority >= PRIORITY_COPILOT

    def _low_cap(self):
        return max(1, self.max_parallel - self.reserved)

    def _can_run(self, ticket):
        if self._running >= self.max_parallel:
            return False
        if self._is_low(ticket[0]) and self._running_low >= self._low_cap():
            return False
        # Theo thứ tự ưu tiên: chỉ vượt lên khi mọi vé đứng trước đều đang bị chặn bởi giới hạn việc nền
        for other in sorted(self._waiting):
            if other == ticket:
                return True
            if not (self._is_low(other[0]) and self._running_low >= self._low_cap()):
                return False
        return False

    def acquire(self, priority, timeout=None):
        """Trả về số giây đã chờ trong hàng đợi."""
        ticket = (priority, next(self._counter))
        started = time.monotonic()
        deadline = None if timeout is None else started + timeout
        with self._cond:
            heapq.heappush(self._waiting, ticket)
            try:
                while not self._can_run(ticket):
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        raise LLMTimeout('Hết thời gian chờ trong hàng đợi LLM')
                    self._cond.wait(remaining)
                self._waiting.remove(ticket)
                heapq.heapify(self._waiting)
                self._running += 1
                if self._is_low(priority):
                    self._running_low += 1
            except BaseException:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                    heapq.heapify(self._waiting)
                self._cond.notify_all()
                raise
        return time.monotonic() - started

    def release(self, priority=None):
        """Trả chỗ. Truyền đúng `priority` đã acquire (stream có thể chạy qua nhiều luồng).
        Không truyền: coi như trả một chỗ việc nền nếu chỉ còn việc nền đang chạy."""
        with self._cond:
            if priority is None:
                low = self._running_low > 0 and self._running_low == self._running
            else:
                low = self._is_low(priority)
            self._running -= 1
            if low:
                self._running_low -= 1
            self._cond.notify_all()

    @property
    def queue_length(self):
        with self._cond:
            return len(self._waiting)


# ============================================================
# Adapters
# ============================================================

class OllamaAdapter:
    name = 'ollama'
    # Ngắt mạch: không kết nối được thì báo lỗi ngay trong khoảng này, khỏi chờ timeout lại
    DOWN_SECONDS = 30.0

    def __init__(self, base_url=None, session=None):
        self.base_url = (base_url or normalize_ollama_base_url()).rstrip('/')
        self.session = session or requests.Session()
        self._down_until = 0.0

    def _payload(self, messages, cfg, schema, stream):
        payload = {
            'model': cfg['model'],
            'messages': messages,
            'stream': stream,
            'think': False,
            'keep_alive': '30m',
            'options': {'temperature': cfg['temperature'], 'num_predict': cfg['max_tokens'],
                        'num_ctx': cfg['num_ctx']},
        }
        if schema is not None:
            payload['format'] = schema
        return payload

    def _post(self, payload, cfg, stream):
        if time.monotonic() < self._down_until:
            raise LLMError(f'Ollama tại {self.base_url} đang không kết nối được (thử lại sau)')
        try:
            response = self.session.post(f'{self.base_url}/api/chat', json=payload, stream=stream,
                                         timeout=(5, cfg['timeout_s']))
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as error:
            self._down_until = time.monotonic() + self.DOWN_SECONDS
            raise LLMError(f'Không kết nối được Ollama tại {self.base_url}') from error
        except requests.exceptions.ReadTimeout as error:
            raise LLMTimeout(f'Ollama trả lời quá {cfg["timeout_s"]}s') from error
        except requests.exceptions.RequestException as error:
            raise LLMError(f'Lỗi kết nối Ollama: {error}') from error
        if response.status_code != 200:
            raise LLMError(f'Ollama HTTP {response.status_code}: {response.text[:300]}')
        return response

    def chat(self, messages, cfg, schema=None):
        data = self._post(self._payload(messages, cfg, schema, False), cfg, False).json()
        return (data.get('message') or {}).get('content', ''), {
            'prompt_tokens': data.get('prompt_eval_count'), 'output_tokens': data.get('eval_count')}

    def chat_tools(self, messages, cfg, tools):
        payload = self._payload(messages, cfg, None, False)
        payload['tools'] = tools
        data = self._post(payload, cfg, False).json()
        message = data.get('message') or {}
        calls = []
        for call in message.get('tool_calls') or []:
            function = call.get('function') or {}
            arguments = function.get('arguments') or {}
            if isinstance(arguments, str):
                arguments = json.loads(arguments or '{}')
            calls.append({'name': function.get('name'), 'arguments': arguments})
        return {'content': message.get('content', ''), 'tool_calls': calls,
                'prompt_tokens': data.get('prompt_eval_count'), 'output_tokens': data.get('eval_count')}

    def stream(self, messages, cfg, stats):
        response = self._post(self._payload(messages, cfg, None, True), cfg, True)
        with response:
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get('error'):
                    raise LLMError(f'Ollama lỗi: {data["error"]}')
                piece = (data.get('message') or {}).get('content')
                if piece:
                    yield piece
                if data.get('done'):
                    stats.prompt_tokens = data.get('prompt_eval_count')
                    stats.output_tokens = data.get('eval_count')
                    break

    def ping(self, model):
        try:
            tags = self.session.get(f'{self.base_url}/api/tags', timeout=5).json()
        except (requests.RequestException, ValueError) as error:
            return False, f'Không kết nối được Ollama tại {self.base_url}: {error}'
        names = [m.get('name', '') for m in tags.get('models', [])]
        if not any(n == model or n.startswith(model + ':') for n in names):
            return False, f'Ollama OK nhưng thiếu model "{model}" (ollama pull {model})'
        return True, f'Ollama OK · {self.base_url} · {model}'


class FakeAdapter:
    """
    Adapter giả lập cho test / chạy thử khi chưa có LLM.
    `responder(messages, cfg, schema)` trả về chuỗi; mặc định trả lời cố định.
    """

    name = 'fake'

    def __init__(self, responder: Optional[Callable] = None, fail: Optional[Exception] = None,
                 tool_responder: Optional[Callable] = None):
        self.responder = responder or self._default
        self.tool_responder = tool_responder
        self.fail = fail
        self.calls = []

    @staticmethod
    def _default(messages, cfg, schema):
        if schema is not None:
            return json.dumps({}, ensure_ascii=False)
        return 'Đây là câu trả lời giả lập (provider "fake").'

    def chat(self, messages, cfg, schema=None):
        self.calls.append({'messages': messages, 'cfg': cfg, 'schema': schema})
        if self.fail:
            raise self.fail
        return self.responder(messages, cfg, schema), {'prompt_tokens': None, 'output_tokens': None}

    def chat_tools(self, messages, cfg, tools):
        """tool_responder(messages, tools) -> {'content': str, 'tool_calls': [{'name', 'arguments'}]}"""
        self.calls.append({'messages': messages, 'cfg': cfg, 'tools': tools})
        if self.fail:
            raise self.fail
        if self.tool_responder is None:
            return {'content': self.responder(messages, cfg, None), 'tool_calls': []}
        return {'tool_calls': [], 'content': '', **self.tool_responder(messages, tools)}

    def stream(self, messages, cfg, stats):
        text, _ = self.chat(messages, cfg)
        for word in text.split(' '):
            yield word + ' '

    def ping(self, model):
        return True, 'Provider giả lập (fake) luôn sẵn sàng'


class OpenAICompatibleAdapter:
    """OpenAI hoặc endpoint tương thích. Mặc định TẮT: dữ liệu khách không ra ngoài (Q-5)."""

    name = 'openai'

    def __init__(self, api_key, base_url):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=300, max_retries=2)

    def chat(self, messages, cfg, schema=None):
        kwargs = {}
        if schema is not None:
            kwargs['response_format'] = {'type': 'json_object'}
        try:
            response = self.client.chat.completions.create(
                model=cfg['model'], messages=messages, temperature=cfg['temperature'],
                max_tokens=cfg['max_tokens'], timeout=cfg['timeout_s'], **kwargs)
        except Exception as error:
            raise LLMError(f'Lỗi OpenAI: {error}') from error
        usage = response.usage
        return response.choices[0].message.content or '', {
            'prompt_tokens': getattr(usage, 'prompt_tokens', None),
            'output_tokens': getattr(usage, 'completion_tokens', None)}

    def chat_tools(self, messages, cfg, tools):
        converted = []
        for m in messages:              # chuyển định dạng tin 'tool' kiểu Ollama sang OpenAI
            if m['role'] == 'tool':
                converted.append({'role': 'tool', 'tool_call_id': m.get('tool_call_id', m.get('tool_name')),
                                  'content': m['content']})
            elif m.get('tool_calls'):
                converted.append({'role': 'assistant', 'content': m.get('content') or '',
                                  'tool_calls': [{'id': c.get('id', c['function']['name']), 'type': 'function',
                                                  'function': {'name': c['function']['name'],
                                                               'arguments': json.dumps(c['function']['arguments'])}}
                                                 for c in m['tool_calls']]})
            else:
                converted.append(m)
        try:
            response = self.client.chat.completions.create(
                model=cfg['model'], messages=converted, temperature=cfg['temperature'],
                max_tokens=cfg['max_tokens'], tools=tools, timeout=cfg['timeout_s'])
        except Exception as error:
            raise LLMError(f'Lỗi OpenAI: {error}') from error
        message = response.choices[0].message
        calls = [{'name': c.function.name, 'arguments': json.loads(c.function.arguments or '{}')}
                 for c in (message.tool_calls or [])]
        return {'content': message.content or '', 'tool_calls': calls}

    def stream(self, messages, cfg, stats):
        try:
            for chunk in self.client.chat.completions.create(
                    model=cfg['model'], messages=messages, temperature=cfg['temperature'],
                    max_tokens=cfg['max_tokens'], stream=True, timeout=cfg['timeout_s']):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as error:
            raise LLMError(f'Lỗi OpenAI: {error}') from error

    def ping(self, model):
        try:
            self.client.models.list()
            return True, 'OpenAI-compatible OK'
        except Exception as error:
            return False, f'Lỗi OpenAI: {error}'


# ============================================================
# Gateway
# ============================================================

class LLMGateway:
    def __init__(self, adapters: dict, max_parallel=2, queue_timeout_s=60.0):
        self.adapters = adapters
        self.limiter = PriorityLimiter(max_parallel)
        self.queue_timeout_s = queue_timeout_s

    def _adapter(self, provider):
        adapter = self.adapters.get(provider)
        if adapter is None:
            raise LLMError(f'Provider "{provider}" chưa được bật')
        return adapter

    @staticmethod
    def _cfg(agent_cfg, model=None):
        return {'model': model or agent_cfg.model, 'temperature': agent_cfg.temperature,
                'max_tokens': agent_cfg.max_tokens, 'num_ctx': agent_cfg.num_ctx,
                'timeout_s': agent_cfg.timeout_s}

    def _targets(self, agent_cfg):
        targets = [(agent_cfg.provider, agent_cfg.model, False)]
        if agent_cfg.fallback_provider and agent_cfg.fallback_model:
            targets.append((agent_cfg.fallback_provider, agent_cfg.fallback_model, True))
        return targets

    def chat(self, agent_cfg, messages, priority, schema=None) -> LLMResult:
        """Gọi không stream. Lỗi model chính -> thử model dự phòng (NFR-3)."""

        if not agent_cfg.enabled:
            raise LLMError(f'Agent {agent_cfg.agent_id} đang tắt')
        last_error = None
        waited = 0.0
        for provider, model, is_fallback in self._targets(agent_cfg):
            waited += self.limiter.acquire(priority, timeout=self.queue_timeout_s)
            started = time.perf_counter()
            try:
                text, usage = self._adapter(provider).chat(messages, self._cfg(agent_cfg, model), schema)
                return LLMResult(text=clean_response(text) if schema is None else text,
                                 provider=provider, model=model,
                                 duration_s=time.perf_counter() - started,
                                 prompt_tokens=usage.get('prompt_tokens'),
                                 output_tokens=usage.get('output_tokens'),
                                 used_fallback=is_fallback, queue_wait_s=waited)
            except LLMError as error:
                last_error = error
            finally:
                self.limiter.release(priority)
        raise last_error

    def chat_tools(self, agent_cfg, messages, priority, tools):
        """
        Một lượt hội thoại có công cụ. Trả về dict: content, tool_calls, provider, model,
        duration_s. Vòng lặp gọi công cụ do tầng dịch vụ điều khiển.
        """

        if not agent_cfg.enabled:
            raise LLMError(f'Agent {agent_cfg.agent_id} đang tắt')
        last_error = None
        for provider, model, is_fallback in self._targets(agent_cfg):
            adapter = self._adapter(provider)
            if not hasattr(adapter, 'chat_tools'):
                last_error = LLMError(f'Provider {provider} không hỗ trợ gọi công cụ')
                continue
            waited = self.limiter.acquire(priority, timeout=self.queue_timeout_s)
            started = time.perf_counter()
            try:
                result = adapter.chat_tools(messages, self._cfg(agent_cfg, model), tools)
                content = clean_response(result.get('content') or '')
                return {**result, 'content': content, 'provider': provider, 'model': model,
                        'used_fallback': is_fallback, 'duration_s': time.perf_counter() - started,
                        'queue_wait_s': waited}
            except LLMError as error:
                last_error = error
            finally:
                self.limiter.release(priority)
        raise last_error

    def stream(self, agent_cfg, messages, priority, stats: StreamStats) -> Iterator[str]:
        """
        Stream văn bản đã lọc <think>. Chỉ chuyển sang model dự phòng nếu lỗi xảy ra
        TRƯỚC khi có chữ nào được gửi đi.
        """

        if not agent_cfg.enabled:
            raise LLMError(f'Agent {agent_cfg.agent_id} đang tắt')
        last_error = None
        for provider, model, is_fallback in self._targets(agent_cfg):
            stats.queue_wait_s += self.limiter.acquire(priority, timeout=self.queue_timeout_s)
            started = time.perf_counter()
            produced = False
            think = ThinkFilter()
            stats.provider, stats.model, stats.used_fallback = provider, model, is_fallback
            try:
                for piece in self._adapter(provider).stream(messages, self._cfg(agent_cfg, model), stats):
                    text = think.feed(piece)
                    if text:
                        produced = True
                        yield text
                tail = think.flush()
                if tail:
                    produced = True
                    yield tail
                if not produced:
                    raise LLMError('Mô hình trả về câu trả lời rỗng')
                stats.duration_s = time.perf_counter() - started
                return
            except LLMError as error:
                if produced:
                    raise
                last_error = error
            finally:
                self.limiter.release(priority)
        raise last_error

    def ping(self, provider, model):
        try:
            return self._adapter(provider).ping(model)
        except LLMError as error:
            return False, str(error)
