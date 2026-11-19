import json
import threading
import time

import pytest

from backend.domain import AgentConfig
from backend.llm.gateway import (
    FakeAdapter,
    LLMError,
    LLMGateway,
    LLMTimeout,
    PriorityLimiter,
    StreamStats,
)


def cfg(**kw):
    return AgentConfig(agent_id='ag1', title='t', provider='fake', model='m', **kw)


def test_chat_strips_think_and_returns_usage():
    gw = LLMGateway({'fake': FakeAdapter(lambda m, c, s: '<think>x</think>Xin chào')})
    result = gw.chat(cfg(), [{'role': 'user', 'content': 'hi'}], priority=2)
    assert result.text == 'Xin chào' and result.provider == 'fake'


def test_structured_output_is_not_cleaned():
    gw = LLMGateway({'fake': FakeAdapter(lambda m, c, s: '{"a": 1}')})
    assert gw.chat(cfg(), [], 1, schema={'type': 'object'}).text == '{"a": 1}'


def test_fallback_model_used_when_primary_fails():
    gw = LLMGateway({'fake': FakeAdapter(fail=LLMError('down')),
                     'backup': FakeAdapter(lambda m, c, s: 'dự phòng')})
    config = cfg(fallback_provider='backup', fallback_model='m2')
    result = gw.chat(config, [], 2)
    assert result.text == 'dự phòng' and result.used_fallback and result.model == 'm2'
    assert result.fallback_reason == 'down' and result.total_s >= result.duration_s


def test_record_result_logs_real_model_and_fallback_reason():
    from backend.domain import AiRun
    from backend.llm.gateway import record_result
    gw = LLMGateway({'fake': FakeAdapter(fail=LLMError('Gemini HTTP 503: high demand')),
                     'backup': FakeAdapter(lambda m, c, s: 'ok')})
    run = AiRun(agent_id='ag3', provider='fake', model='m')
    record_result(run, gw.chat(cfg(fallback_provider='backup', fallback_model='qwen'), [], 3))
    assert (run.provider, run.model, run.status) == ('backup', 'qwen', 'fallback')
    assert '503' in run.error and run.total_s is not None


def test_disabled_agent_raises():
    with pytest.raises(LLMError):
        LLMGateway({'fake': FakeAdapter()}).chat(cfg(enabled=False), [], 2)


def test_stream_filters_think_and_records_stats():
    gw = LLMGateway({'fake': FakeAdapter(lambda m, c, s: '<think>nháp</think> Câu trả lời')})
    stats = StreamStats()
    assert ''.join(gw.stream(cfg(), [], 2, stats)).strip() == 'Câu trả lời'
    assert stats.provider == 'fake' and stats.duration_s > 0


def test_limiter_serves_higher_priority_first():
    limiter = PriorityLimiter(max_parallel=1)
    limiter.acquire(5)                 # đang chạy một việc
    order = []

    def worker(priority, name):
        limiter.acquire(priority)
        order.append(name)
        limiter.release()

    low = threading.Thread(target=worker, args=(5, 'nền'))
    low.start()
    time.sleep(0.05)
    high = threading.Thread(target=worker, args=(1, 'phân loại'))
    high.start()
    time.sleep(0.05)
    limiter.release()
    low.join(2)
    high.join(2)
    assert order == ['phân loại', 'nền']


def test_limiter_queue_timeout():
    limiter = PriorityLimiter(max_parallel=1)
    limiter.acquire(1)
    with pytest.raises(LLMTimeout):
        limiter.acquire(1, timeout=0.05)
    assert limiter.queue_length == 0


def test_ollama_circuit_breaker_fails_fast_after_connection_error():
    import requests
    from backend.llm.gateway import OllamaAdapter

    class DeadSession:
        calls = 0

        def post(self, *args, **kwargs):
            DeadSession.calls += 1
            raise requests.exceptions.ConnectTimeout('timeout')

    adapter = OllamaAdapter(base_url='http://ollama.invalid', session=DeadSession())
    conf = {'model': 'm', 'temperature': 0, 'max_tokens': 5, 'num_ctx': 512, 'timeout_s': 1}
    for _ in range(3):
        with pytest.raises(LLMError):
            adapter.chat([], conf)
    assert DeadSession.calls == 1          # lần 2, 3 báo lỗi ngay, không gọi mạng


def test_chat_tools_returns_calls_and_cleans_content():
    def tools_responder(messages, tools):
        if messages[-1]['role'] == 'tool':
            return {'content': '<think>x</think>Đã xong'}
        return {'tool_calls': [{'name': tools[0]['function']['name'], 'arguments': {'a': 1}}]}

    gw = LLMGateway({'fake': FakeAdapter(tool_responder=tools_responder)})
    tools = [{'type': 'function', 'function': {'name': 'list_staff', 'parameters': {}}}]
    first = gw.chat_tools(cfg(), [{'role': 'user', 'content': 'x'}], 4, tools)
    assert first['tool_calls'] == [{'name': 'list_staff', 'arguments': {'a': 1}}]
    final = gw.chat_tools(cfg(), [{'role': 'tool', 'content': '{}'}], 4, tools)
    assert final['content'] == 'Đã xong' and final['tool_calls'] == []


def test_reserved_slot_keeps_room_for_urgent_work():
    """2 chỗ, giữ 1: gợi ý (ưu tiên 3) chỉ chiếm 1 chỗ; kiểm tra trước khi gửi (2) vào ngay."""
    limiter = PriorityLimiter(max_parallel=2, reserved=1)
    limiter.acquire(3)                                   # gợi ý dài đang chạy
    with pytest.raises(LLMTimeout):
        limiter.acquire(3, timeout=0.05)                 # gợi ý thứ hai phải chờ
    assert limiter.acquire(2, timeout=0.05) < 0.05       # việc gấp không phải chờ
    limiter.release(2)
    limiter.release(3)
    assert limiter.acquire(3, timeout=0.05) < 0.05


def test_single_slot_still_runs_background_work():
    limiter = PriorityLimiter(max_parallel=1, reserved=1)
    assert limiter.acquire(5, timeout=0.05) < 0.05      # 1 chỗ: việc nền không bị chặn vĩnh viễn
    limiter.release(5)


# ---------- Gemini (HTTP giả lập, không gọi mạng) ----------

class _Resp:
    def __init__(self, status, data=None, lines=None):
        self.status_code, self._data, self._lines = status, data or {}, lines or []
        self.text = json.dumps(self._data)

    def json(self):
        return self._data

    def iter_lines(self, decode_unicode=False):
        return iter(self._lines)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, params=None, json=None, stream=False, timeout=None):
        self.calls.append({'url': url, 'body': json, 'params': params})
        return self.responses.pop(0)

    def get(self, url, params=None, timeout=None):
        return self.responses.pop(0)


def _gemini(responses):
    from backend.llm.gateway import GeminiAdapter
    adapter = GeminiAdapter('k', session=_Session(responses))
    adapter.RETRY_DELAYS = (0, 0)
    return adapter


CFG = {'model': 'gemini-x', 'temperature': 0.1, 'max_tokens': 300, 'num_ctx': 0, 'timeout_s': 30}


def _text(text, finish='STOP'):
    return {'candidates': [{'content': {'parts': [{'text': text}]}, 'finishReason': finish}],
            'usageMetadata': {'promptTokenCount': 12, 'candidatesTokenCount': 3}}


def test_gemini_converts_messages_and_schema():
    adapter = _gemini([_Resp(200, _text('{"a": 1}'))])
    text, usage = adapter.chat([{'role': 'system', 'content': 'Bạn là A'},
                                {'role': 'user', 'content': 'hỏi 1'},
                                {'role': 'assistant', 'content': 'đáp 1'},
                                {'role': 'user', 'content': 'hỏi 2'}], CFG, schema={'type': 'object'})
    body = adapter.session.calls[0]['body']
    assert body['systemInstruction']['parts'][0]['text'] == 'Bạn là A'
    assert [c['role'] for c in body['contents']] == ['user', 'model', 'user']
    assert body['generationConfig']['responseJsonSchema'] == {'type': 'object'}
    assert text == '{"a": 1}' and usage == {'prompt_tokens': 12, 'output_tokens': 3}


def test_gemini_retries_overload_then_succeeds():
    adapter = _gemini([_Resp(503, {'error': {'message': 'high demand'}}), _Resp(200, _text('ok'))])
    assert adapter.chat([{'role': 'user', 'content': 'x'}], CFG)[0] == 'ok'
    assert len(adapter.session.calls) == 2


def test_gemini_gives_up_after_retries_so_gateway_can_fall_back():
    adapter = _gemini([_Resp(503, {'error': {'message': 'high demand'}})] * 3)
    with pytest.raises(LLMError, match='503'):
        adapter.chat([{'role': 'user', 'content': 'x'}], CFG)


def test_gemini_truncated_json_is_an_error():
    adapter = _gemini([_Resp(200, _text('{"a":', finish='MAX_TOKENS'))])
    with pytest.raises(LLMError, match='MAX_TOKENS'):
        adapter.chat([{'role': 'user', 'content': 'x'}], CFG, schema={'type': 'object'})


def test_gemini_tool_round_trip_keeps_thought_signature():
    call = {'functionCall': {'name': 'get_operator_metrics', 'args': {'staff': 'Lan'}, 'id': 'c1'},
            'thoughtSignature': 'SIG'}
    adapter = _gemini([_Resp(200, {'candidates': [{'content': {'parts': [call]}}]}),
                       _Resp(200, _text('Nhận định'))])
    tools = [{'type': 'function', 'function': {'name': 'get_operator_metrics', 'description': 'F-2',
                                               'parameters': {'type': 'object', 'properties': {}}}}]
    first = adapter.chat_tools([{'role': 'user', 'content': 'Hiệu suất Lan?'}], CFG, tools)
    assert first['tool_calls'] == [{'name': 'get_operator_metrics', 'arguments': {'staff': 'Lan'}, 'id': 'c1'}]
    history = [{'role': 'user', 'content': 'Hiệu suất Lan?'},
               {'role': 'assistant', 'content': '', 'raw': first['raw'], 'tool_calls': []},
               {'role': 'tool', 'tool_name': 'get_operator_metrics', 'tool_call_id': 'c1',
                'content': '{"total": 1}'}]
    assert adapter.chat_tools(history, CFG, tools)['content'] == 'Nhận định'
    sent = adapter.session.calls[1]['body']['contents']
    assert sent[1]['parts'][0]['thoughtSignature'] == 'SIG'                 # gửi lại nguyên văn
    assert sent[2]['parts'][0]['functionResponse'] == {'name': 'get_operator_metrics',
                                                       'response': {'total': 1}, 'id': 'c1'}


def test_gemini_stream_yields_text():
    lines = ['data: ' + json.dumps(_text('Xin ')), '', 'data: ' + json.dumps(_text('chào'))]
    adapter = _gemini([_Resp(200, lines=lines)])
    from backend.llm.gateway import StreamStats
    stats = StreamStats()
    assert ''.join(adapter.stream([{'role': 'user', 'content': 'x'}], CFG, stats)) == 'Xin chào'
    assert stats.prompt_tokens == 12


def test_remote_provider_not_queued_behind_local_model():
    from backend.llm.gateway import LLMGateway
    gateway = LLMGateway({}, max_parallel=1)
    gateway.limiter.acquire(3)                                  # Ollama đang bận một gợi ý dài
    assert gateway.limiter_for('gemini').acquire(2, timeout=0.05) < 0.05
    gateway.limiter_for('gemini').release(2)
    gateway.limiter.release(3)


# ---------- OpenAI-compatible / OpenRouter (client giả lập) ----------

class _NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Completions:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _openai(replies):
    from backend.llm.gateway import OpenAICompatibleAdapter
    completions = _Completions(replies)
    client = _NS(chat=_NS(completions=completions), models=_NS(list=lambda: []))
    return OpenAICompatibleAdapter('k', 'http://x', name='openrouter', client=client), completions


def _completion(content='', tool_calls=None, finish='stop'):
    return _NS(choices=[_NS(message=_NS(content=content, tool_calls=tool_calls), finish_reason=finish)],
               usage=_NS(prompt_tokens=10, completion_tokens=5))


def test_openai_compatible_falls_back_to_json_object_when_schema_unsupported():
    adapter, completions = _openai([Exception('response_format json_schema is not supported'),
                                    _completion('{"a": 1}'), _completion('{"a": 2}')])
    assert adapter.chat([{'role': 'user', 'content': 'x'}], CFG, schema={'title': 'T', 'type': 'object'})[0] == '{"a": 1}'
    assert completions.calls[0]['response_format']['type'] == 'json_schema'
    assert completions.calls[1]['response_format'] == {'type': 'json_object'}
    adapter.chat([{'role': 'user', 'content': 'y'}], CFG, schema={'title': 'T', 'type': 'object'})
    assert completions.calls[2]['response_format'] == {'type': 'json_object'}       # nhớ theo model


def test_openai_compatible_tool_calls_keep_ids_and_errors_are_named():
    call = _NS(id='call-1', function=_NS(name='get_operator_metrics', arguments='{"staff": "Lan"}'))
    adapter, completions = _openai([_completion(tool_calls=[call]), Exception('429 rate limited')])
    result = adapter.chat_tools([{'role': 'user', 'content': 'x'}], CFG, tools=[])
    assert result['tool_calls'] == [{'name': 'get_operator_metrics', 'arguments': {'staff': 'Lan'}, 'id': 'call-1'}]
    with pytest.raises(LLMError, match='openrouter'):
        adapter.chat_tools([{'role': 'assistant', 'content': '', 'tool_calls': [
            {'function': {'name': 'get_operator_metrics', 'arguments': {'staff': 'Lan'}}, 'id': 'call-1'}]},
            {'role': 'tool', 'tool_name': 'get_operator_metrics', 'tool_call_id': 'call-1', 'content': '{}'}],
            CFG, tools=[])
    sent = completions.calls[1]['messages']
    assert sent[0]['tool_calls'][0]['id'] == 'call-1' and sent[1]['tool_call_id'] == 'call-1'


def test_openai_compatible_truncated_json_is_an_error():
    adapter, _ = _openai([_completion('{"a":', finish='length')])
    with pytest.raises(LLMError, match='cắt cụt'):
        adapter.chat([{'role': 'user', 'content': 'x'}], CFG, schema={'title': 'T'})
