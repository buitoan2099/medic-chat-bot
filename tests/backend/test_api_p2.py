"""Test end-to-end P2 (khung 2 – người trực) qua API, LLM giả lập theo lược đồ đầu ra."""

import json
import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import rag.rag as rag_module
from backend.core import iso, utc_now
from backend.llm.gateway import FakeAdapter
from backend.main import build_state, create_app
from rag.lexical import BM25Index
from tests.conftest import make_chunk

ADMIN = {'X-Admin-Token': 'test-token'}
DRAFT = 'Bạn nên nghỉ ngơi, uống đủ nước và theo dõi nhiệt độ.'


class Brain:
    """LLM giả lập: trả lời theo lược đồ (title của JSON schema) và nội dung prompt."""

    def __init__(self):
        self.guard_issues = []          # issue AG-6 sẽ trả về cho lần kiểm tra kế tiếp
        self.calls = []

    def __call__(self, messages, cfg, schema):
        system, user = messages[0]['content'], messages[-1]['content']
        title = (schema or {}).get('title')
        self.calls.append((title, system, user))
        if title == 'TriageResult':
            asks_treatment = 'nên uống' in user.split('TIN NHẮN MỚI NHẤT CỦA KHÁCH:')[-1]
            return json.dumps(dict(intent='treatment_request' if asks_treatment else 'drug_info',
                                   required_level='C2' if asks_treatment else 'none',
                                   urgency='normal', ai_allowed=not asks_treatment, reason='x'))
        if title == 'CopilotOutput':
            exceeds = 'C1 – TƯ VẤN THÔNG TIN THUỐC' in system and 'nên uống' in user
            return json.dumps({'reply_draft': DRAFT, 'follow_up_questions': ['Bạn bao nhiêu tuổi?'],
                               'internal_notes': 'ghi chú', 'red_flags': [],
                               'scope_check': {'status': 'exceeds' if exceeds else 'within',
                                               'suggested_level': 'C2' if exceeds else None,
                                               'reason': 'hỏi thuốc cụ thể' if exceeds else ''},
                               'monitoring_advice': 'Sốt quá 3 ngày cần đi khám',
                               'confidence': 'medium'}, ensure_ascii=False)
        if title == 'CaseMemoryOutput':
            return json.dumps({'profile': {'allergies': 'penicilin', 'chief_complaint': 'sốt'},
                               'needs_confirmation': [], 'summary': 'Khách sốt, dị ứng penicilin'},
                              ensure_ascii=False)
        if title == 'GuardOutput':
            issues, self.guard_issues = self.guard_issues, []
            verdict = 'block' if {'prescription_drug', 'specific_dose_without_level'} & set(issues) else 'ok'
            return json.dumps({'verdict': verdict, 'issues': issues, 'explanation': 'kiểm tra giả lập'})
        return 'Câu trả lời AI giả lập.'


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('ADMIN_TOKEN', 'test-token')
    bm25 = BM25Index([make_chunk('n1-c01', 'Paracetamol › Liều lượng\nNgười lớn 500 mg.', 'n1', 2,
                                 ['Paracetamol', 'Liều lượng'], 'Liều lượng'),
                      make_chunk('n2-c01', 'Paracetamol › Chỉ định\nHạ sốt, giảm đau.', 'n2', 3,
                                 ['Paracetamol', 'Chỉ định'], 'Chỉ định')])
    monkeypatch.setattr(rag_module, '_bm25', lambda collection=None: bm25)
    brain = Brain()
    adapter = FakeAdapter(brain)

    def factory():
        return build_state(storage_dir=tmp_path / 'storage', adapters={'ollama': adapter},
                           qdrant=False, background='inline', auth_secret='test-secret')

    with TestClient(create_app(factory)) as client:
        staff = {}
        for username, kind, level, roles in [('an', None, None, ['operator']),
                                             ('lan', 'duoc_si', 'C2', ['operator']),
                                             ('minh', 'bac_si', 'C3', ['operator']),
                                             ('quanly', None, None, ['operator', 'manager'])]:
            created = client.post('/api/admin/staff', headers=ADMIN, json={
                'username': username, 'display_name': username.title(), 'password': 'matkhau123',
                'title': 'Dược sĩ' if kind == 'duoc_si' else '', 'roles': roles}).json()
            if kind:
                client.put(f'/api/admin/staff/{created["id"]}/credential', headers=ADMIN,
                           json={'credential': {'kind': kind}, 'verify': True})
                client.post(f'/api/admin/staff/{created["id"]}/grants', headers=ADMIN,
                            json={'key': 'level', 'value': level, 'reason': 'đã xác minh'})
            token = client.post('/api/operator/login', json={'username': username,
                                                             'password': 'matkhau123'}).json()['token']
            headers = {'Authorization': f'Bearer {token}'}
            client.put('/api/operator/presence', headers=headers, json={'status': 'online'})
            staff[username] = {'id': created['id'], 'h': headers}
        yield client, staff, brain


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def customer(client, text='Tôi bị sốt 2 ngày nên uống thuốc gì?'):
    """Khách hỏi ở chế độ AI (bị chuyển người trực vì cần C2) rồi bấm chuyển."""
    conv_id = client.post('/api/chat/conversations', json={'consent': True}).json()['conversation']['id']
    events(client.post(f'/api/chat/conversations/{conv_id}/messages', json={'text': text}))
    client.post(f'/api/chat/conversations/{conv_id}/handoff')
    return conv_id


def queue_ids(client, who):
    return [i['conversation']['id'] for i in client.get('/api/operator/queue', headers=who['h']).json()]


def claim(client, who, conv_id):
    return client.post(f'/api/operator/conversations/{conv_id}/claim', headers=who['h'])


def view(client, who, conv_id):
    return client.get(f'/api/operator/conversations/{conv_id}', headers=who['h'])


def enable_guard(client):
    client.put('/api/admin/settings', headers=ADMIN, json={'changes': {'guard_llm_enabled': True}})


def send(client, who, conv_id, text, **extra):
    return client.post(f'/api/operator/conversations/{conv_id}/send', headers=who['h'],
                       json={'text': text, **extra})


# ---------- đăng nhập ----------

def test_login_and_me(env):
    client, staff, _ = env
    me = client.get('/api/operator/me', headers=staff['lan']['h']).json()
    assert me['effective']['level'] == 'C2' and 'password_hash' not in me
    assert client.get('/api/operator/me').status_code == 401
    assert client.post('/api/operator/login', json={'username': 'lan', 'password': 'sai'}).status_code == 401


# ---------- hàng chờ & tiếp nhận ----------

def test_queue_filtered_by_level(env):                                   # AC-2.1
    client, staff, _ = env
    conv_id = customer(client)
    assert conv_id not in queue_ids(client, staff['an'])                 # C1 không thấy ca C2
    assert conv_id in queue_ids(client, staff['lan'])
    assert conv_id in queue_ids(client, staff['quanly'])                 # quản lý thấy hết


def test_concurrent_claim_only_one_wins(env):                            # AC-2.2
    client, staff, _ = env
    conv_id = customer(client)
    results = {}
    barrier = threading.Barrier(2)

    def worker(name):
        barrier.wait()
        results[name] = claim(client, staff[name], conv_id).status_code

    threads = [threading.Thread(target=worker, args=(n,)) for n in ('lan', 'minh')]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results.values()) == [200, 400]


def test_operator_sees_ai_history_and_copilot_by_level(env):             # AC-1.5, AC-2.3, AC-2.4
    client, staff, brain = env
    conv_id = customer(client)
    assert claim(client, staff['lan'], conv_id).status_code == 200
    data = view(client, staff['lan'], conv_id).json()
    kinds = [m['kind'] for m in data['messages']]
    assert 'handoff_suggestion' in kinds                                 # thấy cả phần chat với AI
    suggestion = data['suggestion']
    assert suggestion['agent_id'] == 'ag3_copilot_c2' and suggestion['reply_draft'] == DRAFT
    assert suggestion['sources'] and 'trang' not in suggestion['reply_draft']
    copilot_prompt = [u for t, _, u in brain.calls if t == 'CopilotOutput'][-1]
    assert 'Dị ứng: penicilin' in copilot_prompt                         # dùng hồ sơ ca từ AG-5


def test_c1_copilot_flags_exceeds(env):                                  # AC-2.5
    client, staff, _ = env
    conv_id = customer(client)
    client.post('/api/manager/assign', headers=staff['quanly']['h'], json={
        'conversation_id': conv_id, 'staff_id': staff['an']['id'], 'reason': 'thử',
        'override_level': True})
    suggestion = view(client, staff['an'], conv_id).json()['suggestion']
    assert suggestion['agent_id'] == 'ag2_copilot_c1'
    assert suggestion['scope_check']['status'] == 'exceeds'


# ---------- gửi tin & kiểm tra trước khi gửi ----------

def test_send_modes_and_suggestion_outcomes(env):                         # AC-2.8
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    suggestion = view(client, staff['lan'], conv_id).json()['suggestion']
    sent = send(client, staff['lan'], conv_id, DRAFT, suggestion_id=suggestion['id']).json()
    assert sent['message']['send_mode'] == 'ai_unedited'
    assert sent['message']['sender_name'] == 'Dược sĩ Lan'                # UI-1.6

    client.post(f'/api/chat/conversations/{conv_id}/messages', json={'text': 'Tôi 30 tuổi'})
    second = view(client, staff['lan'], conv_id).json()['suggestion']
    edited = send(client, staff['lan'], conv_id, DRAFT + ' Nếu sốt cao hãy đi khám.',
                  suggestion_id=second['id']).json()
    assert edited['message']['send_mode'] == 'ai_edited'
    customer_view = client.get(f'/api/chat/conversations/{conv_id}').json()
    assert customer_view['messages'][-1]['sender_type'] == 'staff'


def test_send_unedited_requires_capability(env):                         # AC-2.9
    client, staff, _ = env
    client.post(f'/api/admin/staff/{staff["lan"]["id"]}/grants', headers=ADMIN,
                json={'key': 'ai.send_unedited', 'value': False, 'reason': 'người mới'})
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    suggestion = view(client, staff['lan'], conv_id).json()['suggestion']
    response = send(client, staff['lan'], conv_id, DRAFT, suggestion_id=suggestion['id'])
    assert response.status_code == 400 and 'chỉnh sửa' in response.json()['detail']


def test_typed_message_sends_freely_with_only_a_warning(env):              # trả lời thoải mái
    """Tin tự soạn: vượt quyền / liều cụ thể / chưa nhắc cấp cứu chỉ là cảnh báo, không chặn."""
    client, staff, brain = env
    enable_guard(client)
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    for issue in ('exceeds_level', 'specific_dose_without_level', 'emergency_not_addressed'):
        brain.guard_issues = [issue]
        sent = send(client, staff['lan'], conv_id, f'Tin tự soạn ({issue})')
        assert sent.status_code == 200, sent.json()
        assert sent.json()['check']['verdict'] == 'warn' and not sent.json()['check']['hard_block']


def test_suggestion_based_send_keeps_confirmation(env):                     # AC-2.6
    """Tin từ gợi ý AI vẫn qua AG-6 đầy đủ: block -> cần lý do."""
    client, staff, brain = env
    enable_guard(client)
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    suggestion = view(client, staff['lan'], conv_id).json()['suggestion']
    brain.guard_issues = ['emergency_not_addressed']
    assert send(client, staff['lan'], conv_id, DRAFT, suggestion_id=suggestion['id']).status_code == 400
    brain.guard_issues = ['emergency_not_addressed']
    ok = send(client, staff['lan'], conv_id, DRAFT, suggestion_id=suggestion['id'],
              confirm_reason='đã gọi 115 cho khách')
    assert ok.status_code == 200 and ok.json()['check']['confirmed_reason'] == 'đã gọi 115 cho khách'


def test_typed_rule_only_mode_skips_llm(env):
    client, staff, brain = env
    enable_guard(client)
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    client.put('/api/admin/settings', headers=ADMIN, json={'changes': {'guard_llm_for_typed': False}})
    before = sum(1 for c in brain.calls if c[0] == 'GuardOutput')
    assert send(client, staff['lan'], conv_id, 'Bạn nghỉ ngơi nhé').status_code == 200
    assert sum(1 for c in brain.calls if c[0] == 'GuardOutput') == before      # không gọi AG-6


def test_exceeding_suggestion_cannot_be_sent(env):                          # AC-2.5
    client, staff, _ = env
    conv_id = customer(client)
    client.post('/api/manager/assign', headers=staff['quanly']['h'], json={
        'conversation_id': conv_id, 'staff_id': staff['an']['id'], 'reason': 'thử',
        'override_level': True})
    suggestion = view(client, staff['an'], conv_id).json()['suggestion']
    assert suggestion['scope_check']['status'] == 'exceeds'
    for text in (suggestion['reply_draft'], suggestion['reply_draft'] + ' (đã sửa)'):
        refused = send(client, staff['an'], conv_id, text, suggestion_id=suggestion['id'])
        assert refused.status_code == 400 and 'vượt phạm vi' in refused.json()['detail']
    own = send(client, staff['an'], conv_id, 'Bạn nên đi khám để được tư vấn thuốc phù hợp.')
    assert own.status_code == 200 and own.json()['message']['send_mode'] == 'typed'


def test_prescription_drug_hard_blocked_even_for_doctor(env):             # AC-2.6a
    client, staff, brain = env
    enable_guard(client)
    conv_id = customer(client)
    claim(client, staff['minh'], conv_id)
    brain.guard_issues = ['prescription_drug']
    response = send(client, staff['minh'], conv_id, 'Anh dùng amoxicilin 500 mg',
                    confirm_reason='tôi là bác sĩ')
    assert response.status_code == 400 and 'Tin bị chặn' in response.json()['detail']


def test_citation_leak_warned(env):
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    check = client.post(f'/api/operator/conversations/{conv_id}/check', headers=staff['lan']['h'],
                        json={'text': 'Theo Dược thư 2018, trang 1119, ...'}).json()
    assert 'citation_leak' in check['issues'] and check['verdict'] == 'warn'


# ---------- chuyển / đẩy cấp / đóng / mở lại ----------

def test_transfer_requires_acceptance(env):
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    client.post(f'/api/operator/conversations/{conv_id}/transfer', headers=staff['lan']['h'],
                json={'to_staff_id': staff['minh']['id'], 'note': 'ca nặng'})
    offers = client.get('/api/operator/mine', headers=staff['minh']['h']).json()['transfer_offers']
    assert [c['id'] for c in offers] == [conv_id]
    accepted = client.post(f'/api/operator/conversations/{conv_id}/transfer/respond',
                           headers=staff['minh']['h'], json={'accept': True}).json()
    assert accepted['assignee_id'] == staff['minh']['id']


def test_escalate_returns_to_queue_with_higher_level(env):
    client, staff, _ = env
    conv_id = customer(client, 'Paracetamol là thuốc gì?')
    client.post(f'/api/chat/conversations/{conv_id}/handoff')
    claim(client, staff['an'], conv_id)
    response = client.post(f'/api/operator/conversations/{conv_id}/escalate', headers=staff['an']['h'],
                           json={'level': 'C3', 'reason': 'ca phức tạp'})
    assert response.json()['required_level'] == 'C3' and response.json()['status'] == 'waiting'
    assert conv_id not in queue_ids(client, staff['lan'])
    assert conv_id in queue_ids(client, staff['minh'])


def test_close_and_reopen_within_24h_back_to_same_operator(env):
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    client.post(f'/api/operator/conversations/{conv_id}/close', headers=staff['lan']['h'])
    events(client.post(f'/api/chat/conversations/{conv_id}/messages', json={'text': 'Tôi còn sốt'}))
    conv = client.get(f'/api/chat/conversations/{conv_id}').json()['conversation']
    assert conv['status'] == 'assigned' and conv['assignee_id'] == staff['lan']['id']


def test_message_after_24h_opens_linked_conversation(env):
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    client.post(f'/api/operator/conversations/{conv_id}/close', headers=staff['lan']['h'])
    core = client.app.state.core
    old = core.storage.conversations.get(conv_id)
    core.storage.conversations.update(old.model_copy(update={
        'closed_at': iso(utc_now() - timedelta(hours=25))}), old.version)
    ev = events(client.post(f'/api/chat/conversations/{conv_id}/messages', json={'text': 'Lại sốt'}))
    new_id = next(e['id'] for e in ev if e['type'] == 'conversation')
    assert core.storage.conversations.get(new_id).previous_conversation_id == conv_id


# ---------- SLA, rời ca, quyền xem ----------

def test_sla_breach_marked_once(env):
    client, _, _ = env
    conv_id = customer(client)
    operator = client.app.state.core.operator
    later = utc_now() + timedelta(minutes=6)
    assert operator.check_sla(now=later) == [conv_id]
    assert operator.check_sla(now=later) == []


def test_going_offline_with_active_chat_needs_force(env):
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    response = client.put('/api/operator/presence', headers=staff['lan']['h'], json={'status': 'offline'})
    assert response.status_code == 400
    client.put('/api/operator/presence', headers=staff['lan']['h'],
               json={'status': 'offline', 'force': True})
    assert conv_id in queue_ids(client, staff['minh'])


def test_cannot_view_other_operators_chat(env):
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    assert view(client, staff['an'], conv_id).status_code == 403
    assert view(client, staff['quanly'], conv_id).json()['read_only'] is True


def test_manager_assign_requires_override_for_low_level(env):            # BR-03
    client, staff, _ = env
    conv_id = customer(client)
    body = {'conversation_id': conv_id, 'staff_id': staff['an']['id'], 'reason': 'thiếu người'}
    assert client.post('/api/manager/assign', headers=staff['quanly']['h'], json=body).status_code == 400
    assert client.post('/api/manager/assign', headers=staff['lan']['h'],
                       json=body).status_code == 403                     # không phải quản lý
    ok = client.post('/api/manager/assign', headers=staff['quanly']['h'],
                     json={**body, 'override_level': True})
    assert ok.status_code == 200 and ok.json()['assignee_id'] == staff['an']['id']


def test_view_reports_suggestion_in_progress(env):                         # UI-2.4: đang tạo gợi ý
    client, staff, _ = env
    conv_id = customer(client)
    copilot = client.app.state.core.operator.copilot
    seen = []
    original = copilot._generate

    def spy(*args, **kwargs):                  # nhìn từ người trực trong lúc gợi ý đang tạo
        seen.append(view(client, staff['lan'], conv_id).json()['suggestion_pending_since'])
        return original(*args, **kwargs)

    copilot._generate = spy
    claim(client, staff['lan'], conv_id)
    assert seen and seen[0] is not None
    done = view(client, staff['lan'], conv_id).json()
    assert done['suggestion_pending_since'] is None and done['suggestion']['status'] == 'ready'


def test_manager_replaces_operator_mid_conversation(env):                  # BR-03: thay người trực
    client, staff, _ = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    assert send(client, staff['lan'], conv_id, 'Chào bạn').status_code == 200
    assign = lambda who, **extra: client.post('/api/manager/assign', headers=staff['quanly']['h'], json={  # noqa: E731
        'conversation_id': conv_id, 'staff_id': staff[who]['id'], 'reason': 'vượt thẩm quyền C2', **extra})

    assert assign('an', required_level='C3').status_code == 400          # C1 không đủ cấp C3
    moved = assign('minh', required_level='C3')
    assert moved.status_code == 200
    assert moved.json()['assignee_id'] == staff['minh']['id'] and moved.json()['required_level'] == 'C3'
    assert assign('minh').status_code == 400                             # đang phụ trách rồi

    customer_view = client.get(f'/api/chat/conversations/{conv_id}').json()
    assert 'sẽ tiếp tục hỗ trợ bạn' in customer_view['messages'][-1]['content']
    assert send(client, staff['lan'], conv_id, 'Tin của người cũ').status_code == 400
    assert send(client, staff['minh'], conv_id, 'Tôi là bác sĩ Minh').status_code == 200
    board = client.get('/api/manager/board', headers=staff['quanly']['h']).json()
    item = next(i for i in board['assigned_items'] if i['id'] == conv_id)
    assert item['assignee_id'] == staff['minh']['id'] and item['required_level'] == 'C3'


def test_copilot_not_regenerated_for_same_customer_message(env):
    client, staff, brain = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    count = lambda: sum(1 for c in brain.calls if c[0] == 'CopilotOutput')  # noqa: E731
    before = count()
    copilot = client.app.state.core.operator.copilot
    copilot.mark_pending(conv_id)
    copilot.generate(conv_id, staff['lan']['id'], 'C2')          # cùng tin khách -> dùng lại
    assert count() == before
    client.post(f'/api/operator/conversations/{conv_id}/suggestions', headers=staff['lan']['h'],
                json={'instruction': 'ngắn hơn'})                  # có chỉ dẫn -> vẫn tạo lại
    assert count() == before + 1


def test_no_pre_send_ai_check_by_default(env):                               # gửi ngay, không chờ AG-6
    client, staff, brain = env
    conv_id = customer(client)
    claim(client, staff['lan'], conv_id)
    suggestion = view(client, staff['lan'], conv_id).json()['suggestion']
    before = sum(1 for c in brain.calls if c[0] == 'GuardOutput')
    brain.guard_issues = ['exceeds_level']                       # có bật thì đã bị cảnh báo
    assert send(client, staff['lan'], conv_id, 'Tin tự soạn').status_code == 200
    assert send(client, staff['lan'], conv_id, DRAFT, suggestion_id=suggestion['id']).status_code == 200
    assert sum(1 for c in brain.calls if c[0] == 'GuardOutput') == before
