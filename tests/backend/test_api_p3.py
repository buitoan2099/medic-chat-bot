"""Test end-to-end P3 (khung 3 – quản lý) với AG-7 giả lập theo kịch bản gọi công cụ."""

import json

import pytest
from fastapi.testclient import TestClient

import rag.rag as rag_module
from backend.core import local_date, utc_now
from backend.llm.gateway import FakeAdapter, LLMError
from backend.main import build_state, create_app
from rag.lexical import BM25Index
from tests.conftest import make_chunk

ADMIN = {'X-Admin-Token': 'test-token'}
TODAY = local_date(utc_now())


class Script:
    """AG-7 giả lập: chọn công cụ theo câu hỏi cuối của quản lý, rồi viết nhận định."""

    def __init__(self):
        self.seen = []

    def __call__(self, messages, tools):
        self.seen.append(messages)
        if messages[-1]['role'] == 'tool' or messages[-1]['content'].startswith('[Hệ thống]'):
            return {'content': 'Nhận định: phản hồi nhanh, dùng gợi ý hợp lý.'}
        question = messages[-1]['content']
        call = lambda name, **args: {'tool_calls': [{'name': name, 'arguments': args}]}  # noqa: E731
        if question.startswith('Hiệu suất'):
            return call('get_operator_metrics', staff=question.split()[-1])
        if question.startswith('còn'):                      # câu nối tiếp: dùng lại yêu cầu trước
            return call('get_operator_metrics', staff=question.split()[1])
        if question.startswith('Tóm tắt'):
            return call('get_conversation', conversation=question.split()[-1])
        if question.startswith('Nâng'):
            return call('propose_permission_change', staff=question.split()[1], key='level',
                        value='C2', reason='đủ điều kiện')
        if question.startswith('Tra'):
            return call('search_documents', query='chống chỉ định diclofenac')
        if question.startswith('Ai tên'):
            return call('get_operator_metrics', staff='Nguyễn')
        return {'content': 'Không rõ yêu cầu.'}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('ADMIN_TOKEN', 'test-token')
    bm25 = BM25Index([make_chunk('n2-c01', 'Diclofenac › Chống chỉ định\nLoét dạ dày.', 'n2', 515,
                                 ['Diclofenac', 'Chống chỉ định'], 'Chống chỉ định')])
    monkeypatch.setattr(rag_module, '_bm25', lambda collection=None: bm25)
    script = Script()

    def responder(messages, cfg, schema):
        title = (schema or {}).get('title')
        if title == 'TriageResult':
            return json.dumps(dict(intent='treatment_request', required_level='C1', urgency='normal',
                                   ai_allowed=False, reason='x'))
        if title == 'CopilotOutput':
            return json.dumps({'reply_draft': 'Bạn nên nghỉ ngơi.', 'scope_check': {'status': 'within'}})
        if title == 'CaseMemoryOutput':
            return json.dumps({'profile': {}, 'summary': 'Khách hỏi về sốt'})
        if title == 'GuardOutput':
            return json.dumps({'verdict': 'ok', 'issues': []})
        return 'x'

    adapter = FakeAdapter(responder, tool_responder=script)

    def factory():
        return build_state(storage_dir=tmp_path / 'storage', adapters={'ollama': adapter},
                           qdrant=False, background='inline', auth_secret='s')

    with TestClient(create_app(factory)) as client:
        people = {}
        for username, name, roles, cred in [('lan', 'Nguyễn Lan', ['operator'], 'duoc_si'),
                                            ('hoa', 'Nguyễn Hoa', ['operator'], None),
                                            ('quanly', 'Trần Quản', ['operator', 'manager'], None)]:
            member = client.post('/api/admin/staff', headers=ADMIN, json={
                'username': username, 'display_name': name, 'password': 'matkhau123', 'roles': roles}).json()
            if cred:
                client.put(f'/api/admin/staff/{member["id"]}/credential', headers=ADMIN,
                           json={'credential': {'kind': cred}, 'verify': True})
            token = client.post('/api/operator/login', json={'username': username,
                                                             'password': 'matkhau123'}).json()['token']
            h = {'Authorization': f'Bearer {token}'}
            client.put('/api/operator/presence', headers=h, json={'status': 'online'})
            people[username] = {'id': member['id'], 'h': h}
        # Một cuộc chat được Lan xử lý
        conv = client.post('/api/chat/conversations', json={'consent': True}).json()['conversation']['id']
        client.post(f'/api/chat/conversations/{conv}/messages', json={'text': 'Tôi bị sốt nên uống gì?'})
        client.post(f'/api/chat/conversations/{conv}/handoff')
        client.post(f'/api/operator/conversations/{conv}/claim', headers=people['lan']['h'])
        client.post(f'/api/operator/conversations/{conv}/send', headers=people['lan']['h'],
                    json={'text': 'Bạn nên nghỉ ngơi và theo dõi.'})
        session = client.post('/api/manager/sessions', headers=people['quanly']['h'], json={}).json()['id']
        yield client, people, conv, session, script, adapter


def ask(client, people, session, text):
    return client.post(f'/api/manager/sessions/{session}/ask', headers=people['quanly']['h'],
                       json={'text': text}).json()


def test_operator_metrics_form_matches_metrics_service(env):                    # AC-3.2
    client, people, _, session, _, _ = env
    reply = ask(client, people, session, 'Hiệu suất lan')
    card = reply['cards'][0]
    assert card['form'] == 'F-2' and 'Nhận định' in reply['content']
    m = client.app.state.core.metrics.operator(people['lan']['id'], TODAY, TODAY)
    assert m['conversations']['total'] == 1 and m['ai_usage']['typed'] == 1
    assert f'{m["conversations"]["total"]} cuộc' in card['markdown']


def test_follow_up_uses_session_history(env):                                    # AC-3.5
    client, people, _, session, script, _ = env
    ask(client, people, session, 'Hiệu suất lan')
    reply = ask(client, people, session, 'còn hoa thì sao?')
    history = script.seen[-2]                     # lượt đầu của câu hỏi nối tiếp
    assert any('[đã hiển thị F-2' in m['content'] for m in history if m['role'] == 'assistant')
    assert reply['cards'][0]['form'] == 'F-2' and 'Hoa' in reply['cards'][0]['markdown']


def test_conversation_summary_form(env):                                         # AC-3.1
    client, people, conv, session, _, _ = env
    reply = ask(client, people, session, f'Tóm tắt cuộc chat {conv[-6:]}')
    card = reply['cards'][0]
    assert card['form'] == 'F-1' and card['conversation_id'] == conv
    assert 'Nguyễn Lan' in card['markdown'] and 'AI → người trực' in card['markdown']


def test_ambiguous_name_is_returned_to_agent(env):                               # AC-3.1 (trùng tên)
    client, people, _, session, script, _ = env
    ask(client, people, session, 'Ai tên Nguyễn làm tốt?')
    tool_msg = next(m for m in reversed(script.seen[-1]) if m['role'] == 'tool')
    assert {c['username'] for c in json.loads(tool_msg['content'])['ambiguous']} == {'lan', 'hoa'}


def test_permission_proposal_requires_verified_credential_and_confirmation(env):   # AC-3.3
    client, people, _, session, _, _ = env
    rejected = ask(client, people, session, 'Nâng hoa lên C2')
    assert rejected['cards'] == []                 # chưa xác minh chứng chỉ -> không tạo đề xuất

    reply = ask(client, people, session, 'Nâng lan lên C2')
    proposal = reply['cards'][0]['proposal']
    assert proposal['status'] == 'pending'
    eff = client.get('/api/operator/me', headers=people['lan']['h']).json()['effective']
    assert eff['level'] == 'C1'                    # chưa đổi khi chưa xác nhận
    decided = client.post(f'/api/manager/proposals/{proposal["id"]}/decide',
                          headers=people['quanly']['h'], json={'confirm': True}).json()
    assert decided['status'] == 'confirmed'
    assert client.get('/api/operator/me', headers=people['lan']['h']).json()['effective']['level'] == 'C2'
    again = client.post(f'/api/manager/proposals/{proposal["id"]}/decide',
                        headers=people['quanly']['h'], json={'confirm': True})
    assert again.status_code == 400                # không xác nhận hai lần


def test_document_question_has_citation_data(env):                                # AC-3.4
    client, people, _, session, script, _ = env
    ask(client, people, session, 'Tra chống chỉ định diclofenac')
    tool_msg = next(m for m in reversed(script.seen[-1]) if m['role'] == 'tool')
    results = json.loads(tool_msg['content'])['results']
    assert results[0]['page'] == 515 and 'Diclofenac' in results[0]['title']


def test_quick_adjust_requires_reason_and_is_audited(env):                        # AC-3.6
    client, people, _, _, _, _ = env
    url = f'/api/manager/staff/{people["lan"]["id"]}/grants'
    body = {'key': 'ai.send_unedited', 'value': False, 'source': 'quick_popup'}
    assert client.post(url, headers=people['quanly']['h'], json={**body, 'reason': ''}).status_code == 400
    ok = client.post(url, headers=people['quanly']['h'], json={**body, 'reason': 'người mới'})
    assert ok.json()['capabilities']['ai.send_unedited'] is False
    grants = client.get(f'/api/manager/staff/{people["lan"]["id"]}/grants', headers=people['quanly']['h']).json()
    assert grants[-1]['source'] == 'quick_popup'
    audit = client.app.state.core.storage.audit.by_day(TODAY)
    assert any(a.action == 'permission.grant' and a.data.get('source') == 'quick_popup' for a in audit)


def test_template_and_agent_toggle(env):
    client, people, _, _, _, _ = env
    eff = client.post(f'/api/manager/staff/{people["hoa"]["id"]}/template', headers=people['quanly']['h'],
                      json={'name': 'Dược sĩ mới', 'reason': 'mới vào'}).json()
    assert eff['capabilities']['chat.max_concurrent'] == 3 and eff['capabilities']['ai.send_unedited'] is False
    toggled = client.put('/api/manager/agents/ag4_copilot_c3', headers=people['quanly']['h'],
                         json={'enabled': False, 'reason': 'tạm tắt C3'}).json()
    assert toggled['enabled'] is False


def test_quick_reports_work_without_llm(env):                                     # UI-3.4
    client, people, _, session, _, adapter = env
    adapter.fail = LLMError('Ollama offline')
    reply = client.post(f'/api/manager/sessions/{session}/quick', headers=people['quanly']['h'],
                        json={'action': 'today'}).json()
    assert reply['cards'][0]['form'] == 'F-4' and '1 cuộc chat' in reply['cards'][0]['markdown']
    unavailable = ask(client, people, session, 'Hiệu suất lan')
    assert 'không khả dụng' in unavailable['content']
    stored = client.get(f'/api/manager/sessions/{session}', headers=people['quanly']['h']).json()
    assert len(stored['messages']) == 4                                              # UI-3.5: lưu phiên


def test_board_and_access_control(env):
    client, people, _, _, _, _ = env
    board = client.get('/api/manager/board', headers=people['quanly']['h']).json()
    assert board['assigned'] == 1 and board['on_duty_total'] == 3
    assert client.get('/api/manager/board', headers=people['lan']['h']).status_code == 403


def test_staff_resolved_with_title_and_reminder_after_form(env):
    client, people, _, session, script, _ = env
    core = client.app.state.core
    lan = core.storage.staff.by_username('lan')
    lan.title = 'Dược sĩ'
    core.storage.staff.update(lan)
    assert core.manager.resolve_staff('Dược sĩ Nguyễn Lan').username == 'lan'
    ask(client, people, session, 'Hiệu suất lan')
    final_round = script.seen[-1]
    assert final_round[-1]['role'] == 'user' and 'KHÔNG lặp lại bảng' in final_round[-1]['content']
