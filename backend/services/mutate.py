"""Cập nhật cuộc trò chuyện an toàn khi có nhiều luồng ghi (khoá lạc quan + thử lại)."""

from backend.storage.base import ConflictError


class Rejected(RuntimeError):
    """Điều kiện nghiệp vụ không thoả (vd cuộc chat đã có người nhận)."""


def mutate(storage, conversation_id, change, attempts=5):
    """
    Đọc bản mới nhất, gọi change(conversation) -> dict trường cần đổi (hoặc None nếu
    không đổi; raise Rejected nếu vi phạm điều kiện), ghi với version vừa đọc.
    Xung đột do luồng khác ghi xen giữa -> đọc lại và thử lại.

    Returns:
        Conversation sau khi cập nhật (hoặc bản hiện tại nếu không đổi).
    """

    for _ in range(attempts):
        conversation = storage.conversations.get(conversation_id)
        updates = change(conversation)
        if not updates:
            return conversation
        try:
            return storage.conversations.update(conversation.model_copy(update=updates),
                                                conversation.version)
        except ConflictError:
            continue
    raise ConflictError(f'Cuộc chat {conversation_id} đang được cập nhật liên tục, thử lại sau')
