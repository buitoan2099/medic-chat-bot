"""Test end-to-end API P1 (khung 1 chế độ AI + quản trị) với LLM giả lập, không cần Ollama/Qdrant."""

import json

import pytest
from fastapi.testclient import TestClient

import rag.rag as rag_module
from backend.llm.gateway import FakeAdapter, LLMError
from backend.main import build_state, create_app
from rag.lexical import BM25Index
from tests.conftest import make_chunk

ADMIN = {'X-Admin-Token': 'test-token'}


def triage_json(text):
    """AG-0 giả lập: hỏi liều/thuốc cho bản thân -> C2; còn lại -> thông tin thuốc."""
    if 'nên uống' in text or 'bị sốt' in text:
        data = dict(intent='treatment_request', required_level='C2', urgency='normal',
                    ai_allowed=False, reason='hỏi thuốc cho trường hợp cụ thể')
    else:
        data = dict(intent='drug_info', required_level='none', urgency='normal',
                    ai_allowed=True, reason='thông tin chung')
    return json.dumps(data, ensure_ascii=False)


class Responder:
    def __init__(self):
        self.answer_calls = 0

    def __call__(self, messages, cfg, schema):
        last = messages[-1]['content']
        if schema is not None:
            return triage_json(last.split('TIN NHẮN MỚI NHẤT CỦA KHÁCH:')[-1])
        self.answer_calls += 1
        return 'Chống chỉ định của diclofenac: loét dạ dày tiến triển. Nguồn: Dược thư 2018, tr. 5'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('ADMIN_TOKEN', 'test-token')
    bm25 = BM25Index([
        make_chunk('n2-c01', 'Diclofenac › Chống chỉ định\nLoét dạ dày tiến triển.', 'n2', 5,
                   ['Diclofenac', 'Chống chỉ định'], 'Chống chỉ định'),
        make_chunk('n1-c01', 'Amoxicilin › Liều lượng\nNgười lớn 500 mg mỗi 8 giờ.', 'n1', 2,
                   ['Amoxicilin', 'Liều lượng'], 'Liều lượng'),
    ])
    monkeypatch.setattr(rag_module, '_bm25', lambda collection=None: bm25)
    responder = Responder()
    adapter = FakeAdapter(responder)

    def factory():
        return build_state(storage_dir=tmp_path / 'storage',
                           adapters={'ollama': adapter, 'fake': adapter}, qdrant=False)

    with TestClient(create_app(factory)) as client:
        yield client, responder, adapter


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def start(client):
    response = client.post('/api/chat/conversations', json={'consent': True})
    assert response.status_code == 200
    return response.json()['conversation']['id']


def send(client, conv_id, text):
    return events(client.post(f'/api/chat/conversations/{conv_id}/messages', json={'text': text}))


# ---------- khung 1 ----------

def test_consent_required(setup):
    client, *_ = setup
    assert client.post('/api/chat/conversations', json={'consent': False}).status_code == 400  # AC-1.1


def test_drug_info_answered_from_documents_with_sources(setup):
    client, responder, _ = setup
    conv_id = start(client)
    ev = send(client, conv_id, 'Chống chỉ định của diclofenac là gì?')
    types = [e['type'] for e in ev]
    assert types[0] == 'message' and 'triage' in types and 'token' in types
    done = next(e for e in ev if e['type'] == 'done')['message']                       # AC-1.2
    assert 'loét dạ dày' in done['content'] and done['sender_type'] == 'ai'
    assert done['sources'] and done['sources'][0]['page'] == 5
    assert responder.answer_calls == 1

    view = client.get(f'/api/chat/conversations/{conv_id}').json()
    assert [m['sender_type'] for m in view['messages']] == ['end_user', 'ai']
    assert view['conversation']['days']


def test_treatment_question_redirected_to_operator_without_calling_ai(setup):
    client, responder, _ = setup
    conv_id = start(client)
    ev = send(client, conv_id, 'Tôi bị sốt 39 độ 2 ngày nên uống thuốc gì?')
    system = [e['message'] for e in ev if e['type'] == 'message'][-1]
    assert system['kind'] == 'handoff_suggestion'                                        # AC-1.3
    assert responder.answer_calls == 0
    conv = client.get(f'/api/chat/conversations/{conv_id}').json()['conversation']
    assert conv['required_level'] == 'C2'


def test_emergency_card_by_rules_and_never_downgraded(setup):
    client, responder, _ = setup
    conv_id = start(client)
    ev = send(client, conv_id, 'Mẹ tôi đau ngực, khó thở từ sáng')
    card = [e['message'] for e in ev if e['type'] == 'message'][-1]
    assert card['kind'] == 'emergency' and '115' in card['content']                       # AC-1.4
    assert responder.answer_calls == 0

    send(client, conv_id, 'Chống chỉ định của diclofenac là gì?')
    conv = client.get(f'/api/chat/conversations/{conv_id}').json()['conversation']
    assert conv['urgency'] == 'emergency'                                                 # BR-08b


def test_unaccented_emergency_phrase_detected(setup):
    client, *_ = setup
    conv_id = start(client)
    ev = send(client, conv_id, 'con toi bi kho tho')
    assert [e['message'] for e in ev if e['type'] == 'message'][-1]['kind'] == 'emergency'


def test_llm_down_falls_back_to_safe_default(setup):
    client, responder, adapter = setup
    adapter.fail = LLMError('Ollama offline')
    conv_id = start(client)
    ev = send(client, conv_id, 'Chống chỉ định của diclofenac là gì?')
    triage = next(e for e in ev if e['type'] == 'triage')
    assert triage['source'] == 'fallback' and triage['ai_allowed'] is False
    assert [e['message'] for e in ev if e['type'] == 'message'][-1]['kind'] == 'handoff_suggestion'


def test_handoff_moves_to_queue_and_blocks_ai_mode(setup):
    client, *_ = setup
    conv_id = start(client)
    conv = client.post(f'/api/chat/conversations/{conv_id}/handoff').json()
    assert conv['conversation']['mode'] == 'human'
    assert conv['conversation']['status'] == 'waiting'
    assert conv['messages'][-1]['kind'] == 'notice'
    ev = send(client, conv_id, 'còn câu hỏi khác')
    assert ev[0]['type'] == 'error'


def test_unknown_conversation_404(setup):
    client, *_ = setup
    assert client.get('/api/chat/conversations/khongco').status_code == 404


# ---------- quản trị ----------

def test_admin_requires_token(setup):
    client, *_ = setup
    assert client.get('/api/admin/agents').status_code == 401
    assert client.get('/api/admin/agents', headers={'X-Admin-Token': 'sai'}).status_code == 401


def test_admin_change_model_and_prompt_takes_effect(setup):
    client, _, adapter = setup
    agents = client.get('/api/admin/agents', headers=ADMIN).json()
    assert set(agents) == {'ag0_triage', 'ag1_user_ai'}

    response = client.put('/api/admin/agents/ag1_user_ai', headers=ADMIN,
                          json={'changes': {'model': 'qwen3:4b'}})
    assert response.json()['model'] == 'qwen3:4b'
    created = client.post('/api/admin/agents/ag1_user_ai/prompts', headers=ADMIN,
                          json={'text': 'PROMPT V2', 'note': 'thử', 'activate': True}).json()
    assert created['version'] == 2

    conv_id = start(client)
    send(client, conv_id, 'Chống chỉ định của diclofenac là gì?')
    answer_call = adapter.calls[-1]
    assert answer_call['cfg']['model'] == 'qwen3:4b'                                      # AC-4.1
    assert answer_call['messages'][0]['content'] == 'PROMPT V2'                            # AC-4.2

    versions = client.get('/api/admin/agents/ag1_user_ai/prompts', headers=ADMIN).json()
    assert versions['active'] == 2 and len(versions['versions']) == 2


def test_admin_search_bm25_and_settings(setup):
    client, *_ = setup
    results = client.get('/api/admin/search', headers=ADMIN,
                         params={'q': 'chống chỉ định diclofenac', 'method': 'bm25'}).json()['results']
    assert results[0]['metadata']['node_id'] == 'n2'
    updated = client.put('/api/admin/settings', headers=ADMIN,
                         json={'changes': {'llm_max_parallel': 3}}).json()
    assert updated['llm_max_parallel'] == 3
    assert client.get('/api/health').json()['qdrant_open'] is False
