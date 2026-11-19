"""
Đổi chủ đề trong một cuộc chat: khách chuyển sang hỏi bệnh / vấn đề khác.

Từ tin bắt đầu chủ đề mới, AI (phân loại, trả lời, gợi ý, hồ sơ ca) chỉ đọc phần chat sau mốc.
Hồ sơ ca bỏ các trường về BỆNH CŨ (triệu chứng chính, khởi phát, mức độ, tóm tắt); giữ các
trường về NGƯỜI (tuổi, giới, mang thai, dị ứng, bệnh nền, thuốc đang dùng). Bệnh cũ được lưu
trong sự kiện 'topic_changed' để người trực / quản lý vẫn tra được.

Không hạ cấp cần thiết / độ khẩn của cuộc chat (BR-08b: chỉ nâng).
"""

from backend.domain import ConversationEvent
from backend.services.mutate import mutate

ILLNESS_FIELDS = ('chief_complaint', 'onset', 'severity')


def topic_messages(conversation, messages):
    """Tin thuộc chủ đề hiện tại (id ULID tăng theo thời gian)."""
    start = conversation.topic_start_id
    return [m for m in messages if m.id >= start] if start else list(messages)


def start_new_topic(storage, conversation_id, message_id, actor_type, actor_id=None, reason=''):
    """Đặt mốc chủ đề mới tại `message_id`. Trả về cuộc chat sau cập nhật (hoặc None nếu đã đặt)."""

    before = {}

    def change(conversation):
        if conversation.topic_start_id and conversation.topic_start_id >= message_id:
            return None
        profile = conversation.profile.model_dump()
        before.update({k: profile.get(k) for k in ILLNESS_FIELDS if profile.get(k)})
        before['summary'] = conversation.summary
        for key in ILLNESS_FIELDS:
            profile[key] = None
        profile['needs_confirmation'] = []
        sources = {k: v for k, v in conversation.profile_sources.items() if k not in ILLNESS_FIELDS}
        return {'topic_start_id': message_id, 'profile': conversation.profile.model_validate(profile),
                'profile_sources': sources, 'summary': '', 'summary_upto_message_id': None}

    current = storage.conversations.get(conversation_id)
    updated = mutate(storage, conversation_id, change)
    if updated is None or updated.topic_start_id == current.topic_start_id:
        return None
    storage.events.add(ConversationEvent(conversation_id=conversation_id, type='topic_changed',
                                         actor_type=actor_type, actor_id=actor_id,
                                         data={'message_id': message_id, 'reason': reason,
                                               'previous': before}))
    return updated
