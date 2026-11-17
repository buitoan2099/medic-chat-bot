"""API khung 1 – người dùng (technical plan 5.1, nhóm enduser)."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.common import get_core, sse

router = APIRouter(prefix='/api/chat', tags=['khung 1'])


class StartRequest(BaseModel):
    consent: bool
    display_name: Optional[str] = None
    profile: Optional[dict] = None


class MessageRequest(BaseModel):
    text: str


class ProfileRequest(BaseModel):
    profile: dict


def _view(core, conversation):
    return {'conversation': conversation.model_dump(mode='json'),
            'messages': [m.model_dump(mode='json') for m in core.chat.messages(conversation)]}


@router.post('/conversations')
def start(body: StartRequest, core=Depends(get_core)):
    conversation = core.chat.start(body.consent, body.display_name, body.profile)
    return _view(core, conversation)


@router.get('/conversations/{conversation_id}')
def get(conversation_id: str, core=Depends(get_core)):
    """Mở lại cuộc trò chuyện bằng mã (định danh ẩn danh giai đoạn đầu, plan 5.7)."""
    return _view(core, core.chat.get(conversation_id))


@router.put('/conversations/{conversation_id}/profile')
def update_profile(conversation_id: str, body: ProfileRequest, core=Depends(get_core)):
    return _view(core, core.chat.update_profile(conversation_id, body.profile))


@router.post('/conversations/{conversation_id}/messages')
def send(conversation_id: str, body: MessageRequest, core=Depends(get_core)):
    """Gửi tin ở chế độ AI; trả về stream SSE (xem ChatService.send_ai)."""
    return sse(core.chat.send_ai(conversation_id, body.text))


@router.post('/conversations/{conversation_id}/handoff')
def handoff(conversation_id: str, core=Depends(get_core)):
    conversation, _ = core.chat.handoff(conversation_id)
    return _view(core, conversation)
