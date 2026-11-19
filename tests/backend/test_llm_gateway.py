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
