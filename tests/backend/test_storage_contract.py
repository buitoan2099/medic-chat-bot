"""
Bộ test hợp đồng cho repository (REPO-2): mọi bản cài đặt Storage (local, DB sau
này) phải qua cùng bộ test này. Thêm bản cài đặt mới vào STORAGES.
"""

from datetime import datetime, timezone

import pytest

from backend.core import iso, local_date, new_id
from backend.domain import (
    AgentConfig,
    AiRun,
    Conversation,
    ConversationEvent,
    EndUser,
    Message,
    SenderType,
)
from backend.storage.base import ConflictError, NotFoundError
from backend.storage.local import LocalStorage

STORAGES = {'local': lambda tmp_path: LocalStorage(tmp_path / 'storage')}


@pytest.fixture(params=sorted(STORAGES))
def storage(request, tmp_path):
    return STORAGES[request.param](tmp_path)


def _at(y, m, d, hh, mm):
    return iso(datetime(y, m, d, hh, mm, tzinfo=timezone.utc))


# ---------- tiện ích nền ----------

def test_ids_sortable_and_unique():
    ids = [new_id() for _ in range(2000)]
    assert len(set(ids)) == 2000
    assert ids == sorted(ids)
    assert all(len(i) == 26 for i in ids)


def test_local_date_uses_vietnam_time():
    # 16:59 UTC = 23:59 giờ VN; 17:01 UTC = 00:01 hôm sau giờ VN
    assert local_date(datetime(2026, 11, 17, 16, 59, tzinfo=timezone.utc)) == '2026-11-17'
    assert local_date(datetime(2026, 11, 17, 17, 1, tzinfo=timezone.utc)) == '2026-11-18'


# ---------- người dùng & cuộc chat ----------

def test_end_user_roundtrip_and_update(storage):
    user = storage.end_users.add(EndUser(display_name='A'))
    user.consent_at = _at(2026, 11, 18, 1, 0)
    storage.end_users.update(user)
    assert storage.end_users.get(user.id).consent_at == user.consent_at
    with pytest.raises(NotFoundError):
        storage.end_users.get('khong-ton-tai')


def test_conversation_optimistic_lock(storage):
    conv = storage.conversations.add(Conversation(end_user_id='u1'))
    first = storage.conversations.update(conv.model_copy(update={'status': 'waiting'}), 0)
    assert first.version == 1

    # Người thứ hai vẫn cầm bản cũ (version 0) -> xung đột (BR-01, AC-2.2)
    with pytest.raises(ConflictError):
        storage.conversations.update(conv.model_copy(update={'status': 'assigned'}), 0)
    assert storage.conversations.get(conv.id).status == 'waiting'


def test_conversation_find(storage):
    a = storage.conversations.add(Conversation(end_user_id='u1', days=['2026-11-17']))
    storage.conversations.add(Conversation(end_user_id='u2', days=['2026-11-18']))
    assert [c.id for c in storage.conversations.find(end_user_id='u1')] == [a.id]
    assert [c.id for c in storage.conversations.find(day='2026-11-17')] == [a.id]


# ---------- tin nhắn & sự kiện theo ngày ----------

def test_messages_split_by_vietnam_day_and_read_back_in_order(storage):
    conv_id = 'c1'
    late = storage.messages.add(Message(conversation_id=conv_id, sender_type=SenderType.end_user,
                                        content='23:59', created_at=_at(2026, 11, 17, 16, 59)))
    early = storage.messages.add(Message(conversation_id=conv_id, sender_type=SenderType.ai,
                                         content='00:01', created_at=_at(2026, 11, 17, 17, 1)))
    assert (late.local_date, early.local_date) == ('2026-11-17', '2026-11-18')   # AC-4.3

    assert [m.content for m in storage.messages.by_day('2026-11-17')] == ['23:59']
    assert [m.content for m in storage.messages.by_day('2026-11-18')] == ['00:01']
    both = storage.messages.list(conv_id, ['2026-11-18', '2026-11-17'])
    assert [m.content for m in both] == ['23:59', '00:01']
    assert [m.content for m in storage.messages.list(conv_id, ['2026-11-17', '2026-11-18'], last=1)] == ['00:01']


def test_events_by_day_and_conversation(storage):
    storage.events.add(ConversationEvent(conversation_id='c1', type='created', actor_type='end_user',
                                         created_at=_at(2026, 11, 18, 2, 0)))
    storage.events.add(ConversationEvent(conversation_id='c2', type='created', actor_type='end_user',
                                         created_at=_at(2026, 11, 18, 2, 1)))
    assert len(storage.events.by_day('2026-11-18')) == 2
    assert [e.conversation_id for e in storage.events.for_conversation('c1', ['2026-11-18'])] == ['c1']


def test_ai_runs_by_day(storage):
    storage.ai_runs.add(AiRun(agent_id='ag1', provider='fake', model='m',
                              created_at=_at(2026, 11, 18, 3, 0)))
    assert [r.agent_id for r in storage.ai_runs.by_day('2026-11-18')] == ['ag1']


# ---------- cấu hình ----------

def test_agent_config_and_prompt_versions(storage):
    storage.config.save_agent(AgentConfig(agent_id='ag1', title='AI', model='m1'))
    assert storage.config.get_agents()['ag1'].model == 'm1'

    v1 = storage.config.add_prompt_version('ag1', 'prompt 1', note='khởi tạo')
    v2 = storage.config.add_prompt_version('ag1', 'prompt 2', note='sửa')
    assert (v1.version, v2.version) == (1, 2)
    assert storage.config.get_prompt('ag1', 1) == 'prompt 1'
    assert [v.note for v in storage.config.list_prompt_versions('ag1')] == ['khởi tạo', 'sửa']
    with pytest.raises(NotFoundError):
        storage.config.get_prompt('ag1', 9)


def test_settings_roundtrip(storage):
    assert storage.config.get_settings() == {}
    storage.config.save_settings({'active_collection': 'x'})
    assert storage.config.get_settings()['active_collection'] == 'x'


# ---------- P2: nhân sự, quyền, gợi ý, kiểm tra ----------

from backend.core import id_local_date  # noqa: E402
from backend.domain import AiSuggestion, GuardCheck, PermissionGrant, Staff, StaffPresence  # noqa: E402


def test_id_local_date_matches_creation_day():
    record = AiSuggestion(conversation_id='c', agent_id='a')
    assert id_local_date(record.id) == record.local_date


def test_staff_unique_username_and_update(storage):
    staff = storage.staff.add(Staff(username='lan', display_name='Lan'))
    with pytest.raises(ValueError):
        storage.staff.add(Staff(username='lan', display_name='Lan 2'))
    staff.title = 'Dược sĩ'
    storage.staff.update(staff)
    assert storage.staff.by_username('lan').title == 'Dược sĩ'
    assert len(storage.staff.all()) == 1


def test_permission_history_append_only(storage):
    storage.permissions.add(PermissionGrant(staff_id='s1', kind='level', key='level', value='C1'))
    storage.permissions.add(PermissionGrant(staff_id='s1', kind='level', key='level', value='C2'))
    storage.permissions.add(PermissionGrant(staff_id='s2', kind='level', key='level', value='C3'))
    assert [g.value for g in storage.permissions.for_staff('s1')] == ['C1', 'C2']


def test_presence_current(storage):
    storage.presence.add(StaffPresence(staff_id='s1', status='online'))
    storage.presence.add(StaffPresence(staff_id='s1', status='away'))
    assert storage.presence.current()['s1'].status == 'away'


def test_suggestion_update_latest_wins(storage):
    suggestion = storage.suggestions.add(AiSuggestion(conversation_id='c1', agent_id='ag2'))
    suggestion.outcome = 'edited'
    storage.suggestions.update(suggestion)
    assert storage.suggestions.get(suggestion.id).outcome == 'edited'
    found = storage.suggestions.for_conversation('c1', [suggestion.local_date])
    assert len(found) == 1 and found[0].outcome == 'edited'


def test_guard_check_roundtrip(storage):
    check = storage.guard_checks.add(GuardCheck(conversation_id='c1', staff_id='s1', staff_level='C1',
                                                text='x', verdict='block'))
    check.confirmed_reason = 'đã hỏi bác sĩ'
    storage.guard_checks.update(check)
    assert storage.guard_checks.get(check.id).confirmed_reason == 'đã hỏi bác sĩ'


# ---------- P3: phiên quản lý & đề xuất ----------

from backend.domain import ActionProposal, ManagerMessage, ManagerSession  # noqa: E402


def test_manager_session_messages_and_proposals(storage):
    session = storage.manager.add_session(ManagerSession(manager_id='m1'))
    storage.manager.add_message(ManagerMessage(session_id=session.id, role='user', content='hỏi'))
    storage.manager.add_message(ManagerMessage(session_id=session.id, role='assistant', content='đáp',
                                               cards=[{'type': 'form', 'markdown': '# F-2'}]))
    fresh = storage.manager.get_session(session.id)
    assert [m.role for m in storage.manager.messages(fresh)] == ['user', 'assistant']
    assert [s.id for s in storage.manager.sessions_for('m1')] == [session.id]

    proposal = storage.manager.add_proposal(ActionProposal(manager_id='m1', kind='permission',
                                                           payload={'key': 'level'}))
    proposal.status = 'confirmed'
    storage.manager.update_proposal(proposal)
    assert storage.manager.get_proposal(proposal.id).status == 'confirmed'
