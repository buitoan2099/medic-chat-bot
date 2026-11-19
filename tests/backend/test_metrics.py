"""MetricsService trên một kịch bản có mốc thời gian cố định (BR-11)."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.core import iso
from backend.domain import (
    AiSuggestion,
    Conversation,
    ConversationEvent,
    GuardCheck,
    Message,
    StaffPresence,
)
from backend.services.metrics import MetricsService, days_between, percentile
from backend.storage.local import LocalStorage

T0 = datetime(2026, 11, 18, 2, 0, tzinfo=timezone.utc)      # 09:00 giờ VN
DAY = '2026-11-18'


def at(seconds):
    return iso(T0 + timedelta(seconds=seconds))


@pytest.fixture
def metrics(tmp_path, monkeypatch):
    import backend.core
    # ID (ULID) mang ngày tạo và quyết định thư mục ngày: cố định đồng hồ để dữ liệu mẫu
    # nằm đúng ngày DAY, test không phụ thuộc ngày chạy.
    monkeypatch.setattr(backend.core.time, 'time', lambda: T0.timestamp())
    monkeypatch.setitem(backend.core._last, 'ms', 0)      # bộ sinh ID nhớ ms của lần trước
    st = LocalStorage(tmp_path / 'storage')
    st.conversations.add(Conversation(id='C1', end_user_id='u1', mode='human', status='closed',
                                      required_level='C2', days=[DAY]))
    ev = lambda type_, t, actor=None, actor_type='staff', **data: st.events.add(ConversationEvent(  # noqa: E731
        conversation_id='C1', type=type_, actor_type=actor_type, actor_id=actor, data=data,
        created_at=at(t)))
    msg = lambda sender, t, content, sender_id=None, **kw: st.messages.add(Message(  # noqa: E731
        conversation_id='C1', sender_type=sender, sender_id=sender_id, content=content,
        created_at=at(t), **kw))
    ev('created', -60, 'u1', 'end_user')
    ev('mode_changed', -30, 'u1', 'end_user')
    ev('queued', 0, actor_type='system')
    ev('claimed', 90, 's1')                                     # chờ 90 s
    msg('end_user', -50, 'Tôi bị sốt')
    msg('staff', 150, 'Chào bạn', 's1', send_mode='ai_unedited')   # FRT = 60 s
    msg('end_user', 200, 'Sốt 38 độ')
    msg('staff', 290, 'Bạn uống nước', 's1', send_mode='ai_edited')  # phản hồi = 90 s
    msg('staff', 300, 'Theo dõi thêm', 's1')                     # typed
    ev('closed', 400, 's1')                                     # xử lý = 310 s
    ev('reopened', 500, None, 'end_user', assignee='s1')
    ev('sla_breached', 60, actor_type='system')
    st.suggestions.add(AiSuggestion(conversation_id='C1', staff_id='s1', agent_id='ag3',
                                    edit_ratio=0.2, outcome='edited', created_at=at(250)))
    st.suggestions.add(AiSuggestion(conversation_id='C1', staff_id='s1', agent_id='ag3',
                                    outcome='discarded', created_at=at(260)))
    st.guard_checks.add(GuardCheck(conversation_id='C1', staff_id='s1', staff_level='C2', text='x',
                                   verdict='block', confirmed_reason='đã hỏi', created_at=at(280)))
    st.presence.add(StaffPresence(staff_id='s1', status='online', created_at=at(0)))
    st.presence.add(StaffPresence(staff_id='s1', status='offline', created_at=at(3600)))
    return MetricsService(st)


def test_operator_metrics_match_hand_calculation(metrics):
    m = metrics.operator('s1', DAY, DAY)
    assert m['conversations'] == {'total': 2, 'self_claimed': 1, 'assigned_by_manager': 0,
                                  'transferred_in': 0, 'reopened': 1}
    assert m['first_response']['median_s'] == 60
    assert m['response']['mean_s'] == 90
    assert m['handle']['median_s'] == 310
    assert (m['ai_usage']['ai_unedited'], m['ai_usage']['ai_edited'], m['ai_usage']['typed']) == (1, 1, 1)
    assert m['ai_usage']['mean_edit_ratio'] == 0.2 and m['ai_usage']['suggestions_discarded'] == 1
    assert m['compliance']['blocked_sent_after_confirm'] == 1
    assert m['coordination']['reopen_rate'] == 1.0
    assert m['on_duty_s'] == 3600


def test_overview(metrics):
    o = metrics.overview(DAY, DAY)
    assert o['conversations'] == {'total': 1, 'to_human': 1, 'ai_only': 0, 'end_users': 1}
    assert o['queue']['median_s'] == 90 and o['queue']['sla_breaches'] == 1
    assert o['first_response']['median_s'] == 60
    assert o['by_level'] == {'C2': 1}


def test_other_operator_has_no_data(metrics):
    m = metrics.operator('s2', DAY, DAY)
    assert m['conversations']['total'] == 0 and m['first_response']['median_s'] is None


def test_helpers():
    assert days_between('2026-11-17', '2026-11-18') == ['2026-11-17', '2026-11-18']
    with pytest.raises(ValueError):
        days_between('2026-11-18', '2026-11-17')
    assert percentile([1, 2, 3, 4], 0.5) == 2.5 and percentile([], 0.9) is None


# ---------- form chuẩn ----------

from backend.services import forms  # noqa: E402


def test_forms_render_exact_numbers(metrics):
    m = metrics.operator('s1', DAY, DAY)
    text = forms.operator_performance('Lan', 'C2', m, narrative='Phản hồi nhanh.')
    assert '1′00″' in text                       # FRT 60 s, lấy đúng số đã tính
    assert 'Nhận định (AI' in text and 'Phản hồi nhanh.' in text
    report = forms.operations(metrics.overview(DAY, DAY))
    assert 'quá SLA 1' in report and '1′30″' in report
    table = forms.compare([('Lan', 'C2', m)], DAY, DAY)
    assert '| Lan | C2 | 2 |' in table and 'Trung bình nhóm' in table


def test_quality_form_without_llm_says_not_scored():
    facts = {'code': 'ABC', 'staff': 'Lan', 'required_level': 'C2', 'urgency': 'normal', 'alerts': ''}
    assert 'Chưa chấm điểm' in forms.quality(facts)
