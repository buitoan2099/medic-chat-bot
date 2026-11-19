"""API khung 3 – quản lý (đặc tả 02 mục 3, 5): AG-7, báo cáo, đề xuất, bảng trạng thái, phân quyền."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.common import current_staff, get_core

router = APIRouter(prefix='/api/manager', tags=['khung 3'])


def require_manager(staff=Depends(current_staff)):
    if 'manager' not in staff.roles:
        raise HTTPException(403, 'Cần vai trò quản lý')
    return staff


class SessionCreate(BaseModel):
    title: str = 'Phiên làm việc'


class AskRequest(BaseModel):
    text: str


class QuickRequest(BaseModel):
    action: str
    args: dict[str, Any] = {}


class DecideRequest(BaseModel):
    confirm: bool
    edits: Optional[dict[str, Any]] = None


class GrantRequest(BaseModel):
    key: str
    value: Any
    reason: str
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    source: str = 'settings_page'


class CredentialRequest(BaseModel):
    credential: dict
    verify: bool = False


class TemplateRequest(BaseModel):
    name: str
    reason: str


class AgentToggle(BaseModel):
    enabled: Optional[bool] = None
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    reason: str


def _msg(message):
    return message.model_dump(mode='json')


# ---------- phiên chat với AG-7 ----------

@router.get('/sessions')
def sessions(staff=Depends(require_manager), core=Depends(get_core)):
    return [s.model_dump(mode='json') for s in core.storage.manager.sessions_for(staff.id)]


@router.post('/sessions')
def new_session(body: SessionCreate, staff=Depends(require_manager), core=Depends(get_core)):
    return core.manager.new_session(staff.id, body.title).model_dump(mode='json')


@router.get('/sessions/{session_id}')
def session(session_id: str, staff=Depends(require_manager), core=Depends(get_core)):
    current = core.manager.session(staff.id, session_id)
    return {'session': current.model_dump(mode='json'),
            'messages': [_msg(m) for m in core.storage.manager.messages(current)]}


@router.post('/sessions/{session_id}/ask')
def ask(session_id: str, body: AskRequest, staff=Depends(require_manager), core=Depends(get_core)):
    return _msg(core.manager.ask(staff.id, session_id, body.text))


@router.post('/sessions/{session_id}/quick')
def quick(session_id: str, body: QuickRequest, staff=Depends(require_manager), core=Depends(get_core)):
    return _msg(core.manager.quick(staff.id, session_id, body.action, body.args))


@router.post('/proposals/{proposal_id}/decide')
def decide(proposal_id: str, body: DecideRequest, staff=Depends(require_manager), core=Depends(get_core)):
    return core.manager.decide(staff.id, proposal_id, body.confirm, body.edits).model_dump(mode='json')


# ---------- bảng trạng thái & xem cuộc chat ----------

@router.get('/board')
def board(staff=Depends(require_manager), core=Depends(get_core)):
    return core.metrics.board()


@router.get('/conversations/{conversation_id}')
def conversation(conversation_id: str, staff=Depends(require_manager), core=Depends(get_core)):
    data = core.operator.view(staff.id, conversation_id)          # chỉ đọc, có ghi nhật ký (SEC-6)
    return {'conversation': data['conversation'].model_dump(mode='json'),
            'messages': [m.model_dump(mode='json') for m in data['messages']],
            'events': [e.model_dump(mode='json') for e in data['events']]}


# ---------- phân quyền & điều chỉnh nhanh ----------

@router.get('/staff')
def staff_list(staff=Depends(require_manager), core=Depends(get_core)):
    data, _ = core.manager.run_tool('list_staff', {}, {'manager_id': staff.id})
    # Cảnh báo: người trực có nhiều cảnh báo vượt quyền trong 30 ngày (đặc tả 02 mục 5)
    from datetime import timedelta
    from backend.core import LOCAL_TZ, utc_now
    start = (utc_now() - timedelta(days=29)).astimezone(LOCAL_TZ).strftime('%Y-%m-%d')
    end = utc_now().astimezone(LOCAL_TZ).strftime('%Y-%m-%d')
    from backend.services.metrics import days_between
    checks = [c for day in days_between(start, end) for c in core.storage.guard_checks.by_day(day)]
    for row in data['staff']:
        member = core.storage.staff.get(row['id'])
        row['credential_detail'] = member.credential.model_dump() if member.credential else None
        row['effective'] = core.permissions.effective(member.id)
        row['blocked_30d'] = sum(1 for c in checks if c.staff_id == member.id and c.verdict == 'block')
        row['title'], row['display_name'] = member.title, member.display_name
    return data['staff']


@router.get('/staff/{staff_id}/grants')
def staff_grants(staff_id: str, staff=Depends(require_manager), core=Depends(get_core)):
    return [g.model_dump(mode='json') for g in core.storage.permissions.for_staff(staff_id)]


@router.post('/staff/{staff_id}/grants')
def staff_grant(staff_id: str, body: GrantRequest, staff=Depends(require_manager), core=Depends(get_core)):
    if body.source not in ('settings_page', 'quick_popup'):
        raise HTTPException(400, 'source phải là settings_page | quick_popup')
    core.permissions.grant(staff_id, body.key, body.value, staff.id, body.reason,
                           body.effective_from, body.effective_to, source=body.source)
    return core.permissions.effective(staff_id)


@router.put('/staff/{staff_id}/credential')
def staff_credential(staff_id: str, body: CredentialRequest, staff=Depends(require_manager),
                     core=Depends(get_core)):
    member = core.permissions.set_credential(staff_id, body.credential, staff.id, body.verify)
    return member.model_dump(mode='json', exclude={'password_hash'})


@router.get('/templates')
def templates(staff=Depends(require_manager), core=Depends(get_core)):
    return core.config.settings()['permission_templates']


@router.post('/staff/{staff_id}/template')
def apply_template(staff_id: str, body: TemplateRequest, staff=Depends(require_manager),
                   core=Depends(get_core)):
    template = core.config.settings()['permission_templates'].get(body.name)
    if template is None:
        raise HTTPException(404, f'Không có mẫu "{body.name}"')
    for key, value in template.items():
        core.permissions.grant(staff_id, key, value, staff.id, f'Áp mẫu "{body.name}": {body.reason}',
                               source='settings_page')
    return core.permissions.effective(staff_id)


@router.get('/agents')
def agents(staff=Depends(require_manager), core=Depends(get_core)):
    return {a: {'title': c.title, 'enabled': c.enabled, 'model': c.model,
                'fallback_provider': c.fallback_provider, 'fallback_model': c.fallback_model}
            for a, c in core.config.agents().items()}


@router.put('/agents/{agent_id}')
def toggle_agent(agent_id: str, body: AgentToggle, staff=Depends(require_manager), core=Depends(get_core)):
    """Popup điều chỉnh nhanh – tab Agent: bật/tắt, đổi model dự phòng (cần lý do)."""
    if not body.reason.strip():
        raise HTTPException(400, 'Cần ghi lý do')
    changes = {k: v for k, v in body.model_dump(exclude={'reason'}).items() if v is not None}
    updated = core.config.update_agent(agent_id, changes, actor=f'{staff.id} ({body.reason})')
    return updated.model_dump()
