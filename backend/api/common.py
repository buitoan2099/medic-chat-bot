"""Phụ thuộc dùng chung cho các router."""

import hmac
import json
import logging
import os
from typing import Optional

from fastapi import Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.services.chat_service import ChatError
from backend.storage.base import ConflictError, NotFoundError
from config import ADMIN_TOKEN

log = logging.getLogger('backend')


def get_core(request: Request):
    return request.app.state.core


def current_staff(request: Request, authorization: Optional[str] = Header(default=None)):
    """Nhân sự đăng nhập: header Authorization: Bearer <token>."""

    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'Chưa đăng nhập')
    from backend.services.auth import AuthError
    core = request.app.state.core
    try:
        staff_id = core.signer.verify(authorization.split(' ', 1)[1].strip())
        staff = core.storage.staff.get(staff_id)
    except (AuthError, KeyError):
        raise HTTPException(401, 'Phiên đăng nhập không hợp lệ hoặc đã hết hạn')
    if not staff.active:
        raise HTTPException(401, 'Tài khoản đã bị khoá')
    return staff


def require_admin(x_admin_token: Optional[str] = Header(default=None)):
    """P1: khoá quản trị trong .env (ADMIN_TOKEN). P2 thay bằng đăng nhập nhân sự."""

    token = os.getenv('ADMIN_TOKEN', ADMIN_TOKEN)
    if not token:
        raise HTTPException(503, 'Chưa cấu hình ADMIN_TOKEN trong .env')
    if not x_admin_token or not hmac.compare_digest(x_admin_token, token):
        raise HTTPException(401, 'Sai hoặc thiếu X-Admin-Token')
    return 'admin'


def _event(data):
    return f'data: {json.dumps(data, ensure_ascii=False)}\n\n'


def sse(events):
    """Đóng gói generator sự kiện thành Server-Sent Events; lỗi giữa chừng -> sự kiện error."""

    def stream():
        try:
            for event in events:
                yield _event(event)
        except (ChatError, ConflictError, NotFoundError) as error:
            yield _event({'type': 'error', 'detail': str(error)})
        except Exception as error:   # không để lỗi nội bộ làm treo stream phía UI
            log.exception('Lỗi khi stream')
            yield _event({'type': 'error', 'detail': f'Lỗi hệ thống: {type(error).__name__}'})
        yield _event({'type': 'end'})

    return StreamingResponse(stream(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
