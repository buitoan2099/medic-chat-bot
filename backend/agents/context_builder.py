"""
Dựng ngữ cảnh cho agent theo NGÂN SÁCH TOKEN (technical plan 5.2, xung đột X-6):
không để Ollama cắt ngữ cảnh im lặng. Ước lượng token = ký tự / 2,5 (bảo thủ cho
tiếng Việt), hiệu chỉnh sau bằng prompt_eval_count ghi trong AiRun.
"""

from backend.domain import SenderType

CHARS_PER_TOKEN = 2.5

BUDGET = {
    'system': 2500,
    'profile_summary': 800,
    'history': 4000,
    'documents': 5000,
    'question': 500,
    'output_reserve': 2000,
}

LABELS = {SenderType.end_user: 'Khách', SenderType.ai: 'AI',
          SenderType.staff: 'Người trực', SenderType.system: 'Hệ thống'}

PROFILE_LABELS = {'age': 'Tuổi', 'sex': 'Giới', 'pregnant_or_breastfeeding': 'Mang thai / cho con bú',
                  'allergies': 'Dị ứng', 'conditions': 'Bệnh nền',
                  'current_medications': 'Thuốc đang dùng'}


def tokens(text):
    return int(len(text or '') / CHARS_PER_TOKEN) + 1


def chars(token_budget):
    return int(token_budget * CHARS_PER_TOKEN)


def truncate(text, token_budget):
    limit = chars(token_budget)
    return text if len(text) <= limit else text[:limit].rsplit(' ', 1)[0] + ' …'


def profile_text(conversation):
    lines = [f'- {PROFILE_LABELS[k]}: {v}' for k, v in conversation.profile.model_dump().items() if v]
    text = '\n'.join(lines)
    if conversation.summary:
        text += f'\nTÓM TẮT TRƯỚC ĐÓ: {conversation.summary}'
    return truncate(text, BUDGET['profile_summary'])


def history_lines(messages, token_budget):
    """Các tin gần nhất (mới nhất giữ lại trước) dạng '[Nhãn] nội dung'."""

    picked, used = [], 0
    for message in reversed(messages):
        line = f'[{LABELS[message.sender_type]}] {message.content}'
        cost = tokens(line)
        if used + cost > token_budget:
            break
        picked.append(line)
        used += cost
    return '\n'.join(reversed(picked))


def chat_history(messages, token_budget):
    """Lịch sử dạng hội thoại (user/assistant) cho LLM; bỏ thông báo hệ thống."""

    picked, used = [], 0
    for message in reversed(messages):
        if message.sender_type == SenderType.end_user:
            role = 'user'
        elif message.sender_type in (SenderType.ai, SenderType.staff):
            role = 'assistant'
        else:
            continue
        cost = tokens(message.content)
        if used + cost > token_budget:
            break
        picked.append({'role': role, 'content': message.content})
        used += cost
    return list(reversed(picked))


def build_user_ai_messages(system_prompt, conversation, history, question, documents, triage):
    """
    Messages cho AG-1: system + lịch sử + lượt cuối gồm hồ sơ ca, phân loại, tài liệu, câu hỏi.

    Returns:
        tuple[list[dict], int]: (messages, số token ước lượng của prompt)
    """

    blocks = []
    profile = profile_text(conversation)
    if profile:
        blocks.append(f'HỒ SƠ CA (thông tin khách đã khai báo):\n{profile}')
    if triage is not None:
        blocks.append(f'PHÂN LOẠI: intent={triage.intent}; required_level={triage.required_level}')
    blocks.append(f'TÀI LIỆU:\n{truncate(documents or "(không tìm thấy đoạn tài liệu liên quan)", BUDGET["documents"])}')
    blocks.append(f'CÂU HỎI HIỆN TẠI:\n{truncate(question, BUDGET["question"])}')

    messages = [{'role': 'system', 'content': system_prompt}]
    messages += chat_history(history, BUDGET['history'])
    messages.append({'role': 'user', 'content': '\n\n'.join(blocks)})
    estimate = sum(tokens(m['content']) for m in messages)
    return messages, estimate
