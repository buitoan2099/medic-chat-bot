"""API khung 2 – người trực (technical plan 5.1, nhóm operator) + chỉ định của quản lý."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.common import current_staff, get_core

router = APIRouter(prefix='/api/operator', tags=['khung 2'])
manager_router = APIRouter(prefix='/api/manager', tags=['quản lý'])


def staff_public(staff, eff=None, presence=None):
    data = staff.model_dump(mode='json', exclude={'password_hash'})
    if eff is not None:
        data['effective'] = eff
    if presence is not None:
        data['presence'] = presence
    return data


def conv_dump(conversation):
    return conversation.model_dump(mode='json')


class LoginRequest(BaseModel):
    username: str
    password: str


class PresenceRequest(BaseModel):
    status: str
    force: bool = False


class TextRequest(BaseModel):
    text: str


class SendRequest(BaseModel):
    text: str
    suggestion_id: Optional[str] = None
    guard_check_id: Optional[str] = None
    confirm_reason: Optional[str] = None


class RegenerateRequest(BaseModel):
    instruction: Optional[str] = None


class TransferRequest(BaseModel):
    to_staff_id: str
    note: str = ''


class TransferResponse(BaseModel):
    accept: bool


class EscalateRequest(BaseModel):
    level: str
    reason: str


class ProfileRequest(BaseModel):
    fields: dict


class AssignRequest(BaseModel):
    conversation_id: str
    staff_id: str
    reason: str
    override_level: bool = False


# ---------- đăng nhập & trạng thái ----------

@router.post('/login')
def login(body: LoginRequest, core=Depends(get_core)):
    staff = core.permissions.authenticate(body.username, body.password)
    return {'token': core.signer.sign(staff.id),
            'staff': staff_public(staff, core.permissions.effective(staff.id))}


class DemoLogin(BaseModel):
    username: str


@router.get('/demo-accounts')
def demo_accounts(core=Depends(get_core)):
    """Tài khoản thử để chọn nhanh – chỉ có khi DEMO_MODE bật."""
    from fastapi import HTTPException
    from backend.services.demo import demo_accounts as rows
    if not core.demo:
        raise HTTPException(404, 'Không bật chế độ chạy thử')
    return rows(core.storage, core.permissions)


@router.post('/demo-login')
def demo_login(body: DemoLogin, core=Depends(get_core)):
    from fastapi import HTTPException
    from backend.services.demo import demo_login as login_as
    if not core.demo:
        raise HTTPException(404, 'Không bật chế độ chạy thử')
    staff, token = login_as(core.storage, core.signer, body.username)
    return {'token': token, 'staff': staff_public(staff, core.permissions.effective(staff.id))}


@router.get('/me')
def me(staff=Depends(current_staff), core=Depends(get_core)):
    return staff_public(staff, core.permissions.effective(staff.id),
                        core.permissions.presence(staff.id))


@router.put('/presence')
def presence(body: PresenceRequest, staff=Depends(current_staff), core=Depends(get_core)):
    core.operator.set_presence(staff.id, body.status, body.force)
    return {'presence': core.permissions.presence(staff.id)}


@router.get('/staff/online')
def online_staff(staff=Depends(current_staff), core=Depends(get_core)):
    """Người đang trực (để chọn người nhận khi chuyển)."""
    current = core.storage.presence.current()
    result = []
    for member in core.storage.staff.all():
        if member.id != staff.id and current.get(member.id) and current[member.id].status == 'online':
            eff = core.permissions.effective(member.id)
            result.append({'id': member.id, 'display_name': member.display_name,
                           'title': member.title, 'level': eff['level']})
    return result


# ---------- hàng chờ & cuộc chat ----------

@router.get('/queue')
def queue(staff=Depends(current_staff), core=Depends(get_core)):
    return [{'conversation': conv_dump(i['conversation']), 'waited_s': int(i['waited_s']),
             'sla_breached': i['sla_breached']} for i in core.operator.queue(staff.id)]


@router.get('/mine')
def mine(staff=Depends(current_staff), core=Depends(get_core)):
    data = core.operator.mine(staff.id)
    return {'assigned': [conv_dump(c) for c in data['assigned']],
            'transfer_offers': [conv_dump(c) for c in data['transfer_offers']]}


@router.get('/conversations/{conversation_id}')
def view(conversation_id: str, staff=Depends(current_staff), core=Depends(get_core)):
    data = core.operator.view(staff.id, conversation_id)
    return {'conversation': conv_dump(data['conversation']),
            'messages': [m.model_dump(mode='json') for m in data['messages']],
            'events': [e.model_dump(mode='json') for e in data['events']],
            'suggestion': data['suggestion'].model_dump(mode='json') if data['suggestion'] else None,
            'read_only': data['read_only']}


@router.post('/conversations/{conversation_id}/claim')
def claim(conversation_id: str, staff=Depends(current_staff), core=Depends(get_core)):
    return conv_dump(core.operator.claim(staff.id, conversation_id))


@router.post('/conversations/{conversation_id}/check')
def check(conversation_id: str, body: TextRequest, staff=Depends(current_staff),
          core=Depends(get_core)):
    result = core.operator.check(staff.id, conversation_id, body.text)
    return {**result.model_dump(mode='json'), 'issue_texts': core.operator.guard.describe(result),
            'needs_confirmation': core.operator.guard.needs_confirmation(result)}


@router.post('/conversations/{conversation_id}/send')
def send(conversation_id: str, body: SendRequest, staff=Depends(current_staff),
         core=Depends(get_core)):
    message, check_result = core.operator.send(staff.id, conversation_id, body.text,
                                               body.suggestion_id, body.guard_check_id,
                                               body.confirm_reason)
    return {'message': message.model_dump(mode='json'), 'check': check_result.model_dump(mode='json')}


@router.post('/conversations/{conversation_id}/suggestions')
def regenerate(conversation_id: str, body: RegenerateRequest, staff=Depends(current_staff),
               core=Depends(get_core)):
    core.operator.regenerate(staff.id, conversation_id, body.instruction)
    return {'status': 'đang tạo gợi ý'}


@router.post('/suggestions/{suggestion_id}/discard')
def discard(suggestion_id: str, staff=Depends(current_staff), core=Depends(get_core)):
    return core.operator.discard_suggestion(staff.id, suggestion_id).model_dump(mode='json')


@router.post('/conversations/{conversation_id}/transfer')
def transfer(conversation_id: str, body: TransferRequest, staff=Depends(current_staff),
             core=Depends(get_core)):
    return conv_dump(core.operator.request_transfer(staff.id, conversation_id, body.to_staff_id,
                                                    body.note))


@router.post('/conversations/{conversation_id}/transfer/respond')
def transfer_respond(conversation_id: str, body: TransferResponse, staff=Depends(current_staff),
                     core=Depends(get_core)):
    return conv_dump(core.operator.respond_transfer(staff.id, conversation_id, body.accept))


@router.post('/conversations/{conversation_id}/escalate')
def escalate(conversation_id: str, body: EscalateRequest, staff=Depends(current_staff),
             core=Depends(get_core)):
    return conv_dump(core.operator.escalate(staff.id, conversation_id, body.level, body.reason))


@router.post('/conversations/{conversation_id}/close')
def close(conversation_id: str, staff=Depends(current_staff), core=Depends(get_core)):
    return conv_dump(core.operator.close(staff.id, conversation_id))


@router.put('/conversations/{conversation_id}/profile')
def profile(conversation_id: str, body: ProfileRequest, staff=Depends(current_staff),
            core=Depends(get_core)):
    return conv_dump(core.operator.update_profile(staff.id, conversation_id, body.fields))


# ---------- quản lý: chỉ định (BR-03) ----------

@manager_router.post('/assign')
def assign(body: AssignRequest, staff=Depends(current_staff), core=Depends(get_core)):
    return conv_dump(core.operator.assign(staff.id, body.conversation_id, body.staff_id,
                                          body.reason, body.override_level))
