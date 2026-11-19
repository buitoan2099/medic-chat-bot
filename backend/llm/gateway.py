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
    fallback_reason: Optional[str] = None     # lỗi của model chính khi phải dùng dự phòng
    total_s: float = 0.0                      # cả thời gian các lần thử lỗi trước đó


def record_result(run, result):
    """Ghi kết quả gọi LLM vào AiRun: model THỰC SỰ trả lời, thời gian, token, lý do dự phòng."""
    run.provider, run.model = result.provider, result.model
    run.duration_s, run.queue_wait_s = result.duration_s, result.queue_wait_s
    run.prompt_tokens, run.output_tokens = result.prompt_tokens, result.output_tokens
    run.total_s = result.total_s or result.duration_s
    if result.used_fallback:
        run.status, run.error = 'fallback', f'Model chính lỗi, đã dùng dự phòng: {result.fallback_reason}'[:500]


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
    fallback_reason: Optional[str] = None
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
    """
    OpenAI hoặc endpoint tương thích (OpenRouter, vLLM…). Mỗi endpoint một provider riêng (`name`).
    Mặc định TẮT: dữ liệu khách không ra ngoài khi chưa cấu hình khoá (Q-5).
    """

    MAX_READ_TIMEOUT_S = 90.0        # model miễn phí có thể chậm; quá mức này thì chuyển dự phòng

    def __init__(self, api_key, base_url, name='openai', client=None):
        self.name = name
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=self.MAX_READ_TIMEOUT_S,
                            max_retries=2)              # SDK tự thử lại khi 429 / 5xx
        self.client = client
        self._json_schema_ok = {}                       # model -> có nhận response_format json_schema

    def _timeout(self, cfg):
        return min(cfg['timeout_s'], self.MAX_READ_TIMEOUT_S)

    def _error(self, error):
        return LLMError(f'Lỗi {self.name}: {str(error)[:300]}')

    def _create(self, cfg, messages, **kwargs):
        return self.client.chat.completions.create(
            model=cfg['model'], messages=messages, temperature=cfg['temperature'],
            # model có suy nghĩ (reasoning) dùng thêm token -> nới để không bị cắt cụt
            max_tokens=max(int(cfg['max_tokens']) * 4, 2048), timeout=self._timeout(cfg), **kwargs)

    @staticmethod
    def _usage(response):
        usage = getattr(response, 'usage', None)
        return {'prompt_tokens': getattr(usage, 'prompt_tokens', None),
                'output_tokens': getattr(usage, 'completion_tokens', None)}

    def chat(self, messages, cfg, schema=None):
        model = cfg['model']
        try:
            if schema is not None and self._json_schema_ok.get(model, True):
                try:
                    response = self._create(cfg, messages, response_format={
                        'type': 'json_schema',
                        'json_schema': {'name': schema.get('title', 'Output'), 'strict': False, 'schema': schema}})
                    self._json_schema_ok[model] = True
                except Exception as error:      # model không hỗ trợ lược đồ -> JSON thường
                    if 'response_format' not in str(error) and 'json_schema' not in str(error):
                        raise
                    self._json_schema_ok[model] = False
                    response = self._create(cfg, messages, response_format={'type': 'json_object'})
            elif schema is not None:
                response = self._create(cfg, messages, response_format={'type': 'json_object'})
            else:
                response = self._create(cfg, messages)
        except LLMError:
            raise
        except Exception as error:
            raise self._error(error) from error
        choice = response.choices[0]
        if schema is not None and getattr(choice, 'finish_reason', None) == 'length':
            raise LLMError(f'{self.name} bị cắt cụt khi trả JSON – tăng "Token tối đa"')
        return choice.message.content or '', self._usage(response)

    @staticmethod
    def _convert_tools_messages(messages):
        converted = []
        for m in messages:              # chuyển định dạng tin 'tool' kiểu Ollama sang OpenAI
            if m['role'] == 'tool':
                converted.append({'role': 'tool', 'tool_call_id': m.get('tool_call_id') or m.get('tool_name'),
                                  'content': m['content']})
            elif m.get('tool_calls'):
                calls = []
                for c in m['tool_calls']:
                    function = c.get('function') or c
                    calls.append({'id': c.get('id') or function.get('id') or function['name'], 'type': 'function',
                                  'function': {'name': function['name'],
                                               'arguments': json.dumps(function.get('arguments') or {},
                                                                       ensure_ascii=False)}})
                converted.append({'role': 'assistant', 'content': m.get('content') or '', 'tool_calls': calls})
            else:
                converted.append({k: v for k, v in m.items() if k in ('role', 'content')})
        return converted

    def chat_tools(self, messages, cfg, tools):
        try:
            response = self._create(cfg, self._convert_tools_messages(messages), tools=tools)
        except Exception as error:
            raise self._error(error) from error
        message = response.choices[0].message
        calls = []
        for c in message.tool_calls or []:
            try:
                arguments = json.loads(c.function.arguments or '{}')
            except ValueError:
                arguments = {}
            calls.append({'name': c.function.name, 'arguments': arguments, 'id': c.id})
        return {'content': message.content or '', 'tool_calls': calls, **self._usage(response)}

    def stream(self, messages, cfg, stats):
        try:
            for chunk in self._create(cfg, messages, stream=True, stream_options={'include_usage': True}):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                if getattr(chunk, 'usage', None):
                    stats.prompt_tokens = chunk.usage.prompt_tokens
                    stats.output_tokens = chunk.usage.completion_tokens
        except Exception as error:
            raise self._error(error) from error

    def ping(self, model):
        try:
            ids = {m.id for m in self.client.models.list()}
        except Exception as error:
            return False, f'Lỗi {self.name}: {str(error)[:200]}'
        if ids and model not in ids:
            return False, f'{self.name} OK nhưng không có model "{model}"'
        return True, f'{self.name} OK · {model}'


class GeminiAdapter:
    """
    Google Gemini qua REST (generativelanguage.googleapis.com, khoá GEMINI_API_KEY).

    - Đầu ra có cấu trúc: generationConfig.responseJsonSchema (nhận thẳng JSON Schema của pydantic).
    - Gọi công cụ: functionDeclarations. Gemini 3 trả `thoughtSignature` kèm functionCall và BẮT BUỘC
      gửi lại nguyên văn ở lượt sau -> giữ phần thô trong 'raw' của tin assistant.
    - 429/503 (quá tải) -> thử lại có giãn cách; vẫn lỗi thì gateway chuyển sang model dự phòng.
    """

    name = 'gemini'
    BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/models'
    RETRY_STATUS = (429, 500, 503)
    RETRY_DELAYS = (1.5, 4.0)
    # Gợi ý / trả lời bình thường mất 3–10 s; treo lâu hơn mức này thì chuyển sang dự phòng sớm
    MAX_READ_TIMEOUT_S = 45.0

    def __init__(self, api_key, session=None):
        self.api_key = api_key
        self.session = session or requests.Session()

    # ---------- chuyển đổi định dạng ----------

    @staticmethod
    def _convert(messages):
        """messages kiểu OpenAI/Ollama -> (systemInstruction, contents) của Gemini."""
        system, contents = [], []

        def add(role, parts):
            if contents and contents[-1]['role'] == role:
                contents[-1]['parts'].extend(parts)          # Gemini cần xen kẽ user/model
            else:
                contents.append({'role': role, 'parts': list(parts)})

        for message in messages:
            role, text = message.get('role'), message.get('content') or ''
            if role == 'system':
                system.append(text)
            elif role == 'assistant':
                if message.get('raw'):
                    add('model', message['raw'])
                else:
                    parts = [{'text': text}] if text else []
                    for call in message.get('tool_calls') or []:
                        function = call.get('function') or call
                        parts.append({'functionCall': {'name': function['name'],
                                                       'args': function.get('arguments') or {}}})
                    add('model', parts or [{'text': ''}])
            elif role == 'tool':
                try:
                    response = json.loads(text)
                except ValueError:
                    response = {'content': text}
                if not isinstance(response, dict):
                    response = {'content': response}
                part = {'functionResponse': {'name': message.get('tool_name') or 'tool',
                                             'response': response}}
                if message.get('tool_call_id'):
                    part['functionResponse']['id'] = message['tool_call_id']
                add('user', [part])
            else:
                add('user', [{'text': text}])
        instruction = {'parts': [{'text': '\n\n'.join(system)}]} if system else None
        return instruction, contents

    @staticmethod
    def _tools(tools):
        declarations = []
        for tool in tools or []:
            function = tool.get('function') or tool
            declarations.append({'name': function['name'], 'description': function.get('description', ''),
                                 'parameters': function.get('parameters') or {'type': 'object', 'properties': {}}})
        return [{'functionDeclarations': declarations}] if declarations else None

    def _body(self, messages, cfg, schema=None, tools=None):
        instruction, contents = self._convert(messages)
        # Model Gemini 3 có "suy nghĩ" ẩn tính vào giới hạn token ra -> nới để không bị cắt cụt
        generation = {'temperature': cfg['temperature'],
                      'maxOutputTokens': max(int(cfg['max_tokens']) * 4, 2048)}
        if schema is not None:
            generation.update(responseMimeType='application/json', responseJsonSchema=schema)
        body = {'contents': contents, 'generationConfig': generation}
        if instruction:
            body['systemInstruction'] = instruction
        declared = self._tools(tools)
        if declared:
            body['tools'] = declared
        return body

    @staticmethod
    def _parts(data):
        candidates = data.get('candidates') or []
        if not candidates:
            reason = (data.get('promptFeedback') or {}).get('blockReason')
            raise LLMError(f'Gemini không trả nội dung (blockReason={reason})')
        candidate = candidates[0]
        if candidate.get('finishReason') in ('SAFETY', 'PROHIBITED_CONTENT', 'BLOCKLIST'):
            raise LLMError(f'Gemini chặn nội dung (finishReason={candidate["finishReason"]})')
        return (candidate.get('content') or {}).get('parts') or [], candidate.get('finishReason')

    @staticmethod
    def _usage(data):
        usage = data.get('usageMetadata') or {}
        return {'prompt_tokens': usage.get('promptTokenCount'),
                'output_tokens': usage.get('candidatesTokenCount')}

    # ---------- HTTP ----------

    def _post(self, model, action, body, cfg, stream=False):
        if not self.api_key:
            raise LLMError('Chưa cấu hình GEMINI_API_KEY trong .env')
        params = {'key': self.api_key}
        if stream:
            params['alt'] = 'sse'
        url = f'{self.BASE_URL}/{model}:{action}'
        for attempt in range(len(self.RETRY_DELAYS) + 1):
            try:
                read_timeout = min(cfg['timeout_s'], self.MAX_READ_TIMEOUT_S)
                response = self.session.post(url, params=params, json=body, stream=stream,
                                             timeout=(10, read_timeout))
            except requests.exceptions.ReadTimeout as error:
                raise LLMTimeout(f'Gemini không trả lời sau {read_timeout:.0f}s') from error
            except requests.exceptions.RequestException as error:
                raise LLMError(f'Lỗi kết nối Gemini: {type(error).__name__}') from error
            if response.status_code == 200:
                return response
            if response.status_code in self.RETRY_STATUS and attempt < len(self.RETRY_DELAYS):
                response.close()
                time.sleep(self.RETRY_DELAYS[attempt])
                continue
            try:
                detail = response.json().get('error', {}).get('message', '')
            except ValueError:
                detail = response.text
            raise LLMError(f'Gemini HTTP {response.status_code}: {detail[:300]}')

    # ---------- giao diện adapter ----------

    def chat(self, messages, cfg, schema=None):
        data = self._post(cfg['model'], 'generateContent', self._body(messages, cfg, schema), cfg).json()
        parts, finish = self._parts(data)
        text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
        if finish == 'MAX_TOKENS' and schema is not None:
            raise LLMError('Gemini bị cắt cụt (MAX_TOKENS) khi trả JSON – tăng "Token tối đa"')
        return text, self._usage(data)

    def chat_tools(self, messages, cfg, tools):
        data = self._post(cfg['model'], 'generateContent', self._body(messages, cfg, tools=tools), cfg).json()
        parts, _ = self._parts(data)
        calls = [{'name': p['functionCall']['name'], 'arguments': p['functionCall'].get('args') or {},
                  'id': p['functionCall'].get('id')} for p in parts if p.get('functionCall')]
        text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
        return {'content': text, 'tool_calls': calls, 'raw': parts, **self._usage(data)}

    def stream(self, messages, cfg, stats):
        response = self._post(cfg['model'], 'streamGenerateContent', self._body(messages, cfg), cfg,
                              stream=True)
        response.encoding = 'utf-8'           # SSE của Gemini không ghi charset -> requests đoán sai
        with response:
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith('data:'):
                    continue
                data = json.loads(line[5:].strip())
                parts, _ = self._parts(data)
                for part in parts:
                    if part.get('text') and not part.get('thought'):
                        yield part['text']
                usage = self._usage(data)
                if usage['prompt_tokens']:
                    stats.prompt_tokens, stats.output_tokens = usage['prompt_tokens'], usage['output_tokens']

    def ping(self, model):
        if not self.api_key:
            return False, 'Chưa cấu hình GEMINI_API_KEY trong .env'
        try:
            response = self.session.get(f'{self.BASE_URL}/{model}', params={'key': self.api_key}, timeout=10)
        except requests.RequestException as error:
            return False, f'Không kết nối được Gemini: {type(error).__name__}'
        if response.status_code != 200:
            try:
                detail = response.json().get('error', {}).get('message', '')
            except ValueError:
                detail = response.text
            return False, f'Gemini HTTP {response.status_code}: {detail[:200]}'
        return True, f'Gemini OK · {model}'


# ============================================================
# Gateway
# ============================================================

class LLMGateway:
    # Nhà cung cấp chạy trên máy mình (giới hạn bởi phần cứng) dùng `limiter` chung theo
    # llm_max_parallel; dịch vụ đám mây có hàng đợi riêng, song song nhiều hơn.
    LOCAL_PROVIDERS = ('ollama', 'fake')

    def __init__(self, adapters: dict, max_parallel=2, queue_timeout_s=60.0, remote_parallel=8):
        self.adapters = adapters
        self.limiter = PriorityLimiter(max_parallel)
        self.remote_limiters = {}
        self.remote_parallel = remote_parallel
        self.queue_timeout_s = queue_timeout_s

    def limiter_for(self, provider):
        if provider in self.LOCAL_PROVIDERS:
            return self.limiter
        if provider not in self.remote_limiters:
            self.remote_limiters[provider] = PriorityLimiter(self.remote_parallel, reserved=0)
        return self.remote_limiters[provider]

    def set_remote_parallel(self, value):
        self.remote_parallel = max(1, int(value))
        for limiter in self.remote_limiters.values():
            limiter.set_max_parallel(self.remote_parallel)

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
        begun = time.perf_counter()
        for provider, model, is_fallback in self._targets(agent_cfg):
            limiter = self.limiter_for(provider)
            waited += limiter.acquire(priority, timeout=self.queue_timeout_s)
            started = time.perf_counter()
            try:
                text, usage = self._adapter(provider).chat(messages, self._cfg(agent_cfg, model), schema)
                return LLMResult(text=clean_response(text) if schema is None else text,
                                 provider=provider, model=model,
                                 duration_s=time.perf_counter() - started,
                                 prompt_tokens=usage.get('prompt_tokens'),
                                 output_tokens=usage.get('output_tokens'),
                                 used_fallback=is_fallback, queue_wait_s=waited,
                                 fallback_reason=str(last_error) if is_fallback and last_error else None,
                                 total_s=time.perf_counter() - begun)
            except LLMError as error:
                last_error = error
            finally:
                limiter.release(priority)
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
            limiter = self.limiter_for(provider)
            waited = limiter.acquire(priority, timeout=self.queue_timeout_s)
            started = time.perf_counter()
            try:
                result = adapter.chat_tools(messages, self._cfg(agent_cfg, model), tools)
                content = clean_response(result.get('content') or '')
                return {**result, 'content': content, 'provider': provider, 'model': model,
                        'used_fallback': is_fallback, 'duration_s': time.perf_counter() - started,
                        'queue_wait_s': waited,
                        'fallback_reason': str(last_error) if is_fallback and last_error else None}
            except LLMError as error:
                last_error = error
            finally:
                limiter.release(priority)
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
            limiter = self.limiter_for(provider)
            stats.queue_wait_s += limiter.acquire(priority, timeout=self.queue_timeout_s)
            started = time.perf_counter()
            produced = False
            think = ThinkFilter()
            stats.provider, stats.model, stats.used_fallback = provider, model, is_fallback
            if is_fallback and last_error:
                stats.fallback_reason = str(last_error)
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
                limiter.release(priority)
        raise last_error

    def ping(self, provider, model):
        try:
            return self._adapter(provider).ping(model)
        except LLMError as error:
            return False, str(error)
