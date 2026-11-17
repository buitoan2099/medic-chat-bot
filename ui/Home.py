"""
Khung 1 – Người dùng (đặc tả 02 mục 1). Chạy:

    streamlit run ui/Home.py

Yêu cầu backend đang chạy (BACKEND_URL trong .env).
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import APP_NOTICE, APP_SUBTITLE, APP_TITLE  # noqa: E402
from ui import api_client as api  # noqa: E402

st.set_page_config(page_title=APP_TITLE, page_icon='💬', layout='centered')

PROFILE_FIELDS = {'age': 'Tuổi', 'sex': 'Giới tính',
                  'pregnant_or_breastfeeding': 'Đang mang thai / cho con bú?',
                  'allergies': 'Dị ứng thuốc (nếu có)', 'conditions': 'Bệnh nền (nếu có)',
                  'current_medications': 'Thuốc đang dùng (nếu có)'}

state = st.session_state
state.setdefault('conversation_id', None)


def reset():
    state.conversation_id = None


# ---------- kết nối backend ----------

try:
    api.health()
except api.BackendError as error:
    st.error('Không kết nối được máy chủ. Vui lòng thử lại sau.')
    st.caption(str(error))
    st.stop()

# ---------- thanh bên ----------

with st.sidebar:
    st.subheader('Cuộc trò chuyện')
    if state.conversation_id:
        st.caption('Mã cuộc trò chuyện (lưu lại để mở tiếp):')
        st.code(state.conversation_id, language=None)
        st.button('➕ Cuộc trò chuyện mới', on_click=reset, width='stretch')
    resume = st.text_input('Mở lại bằng mã', placeholder='Dán mã cuộc trò chuyện')
    if st.button('Mở lại', width='stretch', disabled=not resume.strip()):
        try:
            api.get_conversation(resume.strip())
            state.conversation_id = resume.strip()
            st.rerun()
        except api.BackendError:
            st.error('Không tìm thấy cuộc trò chuyện với mã này.')

st.title(APP_TITLE)
st.caption(APP_SUBTITLE)

# ---------- bắt đầu: đồng ý + chọn chế độ (UI-1.1) ----------

if not state.conversation_id:
    st.info(
        (APP_NOTICE + '\n\n' if APP_NOTICE else '')
        + 'Đây là kênh hỗ trợ tham khảo, **không thay thế khám bệnh**. Nội dung trò chuyện được '
        'lưu lại để phục vụ tư vấn. **Trường hợp cấp cứu, hãy gọi 115.**')
    with st.form('start'):
        consent = st.checkbox('Tôi đã đọc và đồng ý')
        mode = st.radio('Bạn muốn trò chuyện với', ['🤖 AI (tra cứu tài liệu)', '🧑‍⚕️ Người trực'],
                        horizontal=True)
        with st.expander('Thông tin giúp tư vấn (không bắt buộc)'):
            profile = {key: st.text_input(label) for key, label in PROFILE_FIELDS.items()}
        submitted = st.form_submit_button('Bắt đầu', type='primary')
    if submitted:
        if not consent:
            st.warning('Vui lòng đánh dấu đồng ý để bắt đầu.')
            st.stop()
        view = api.start_conversation(True, {k: v for k, v in profile.items() if v.strip()} or None)
        state.conversation_id = view['conversation']['id']
        if mode.startswith('🧑'):
            api.handoff(state.conversation_id)
        st.rerun()
    st.stop()

# ---------- cuộc trò chuyện ----------

try:
    view = api.get_conversation(state.conversation_id)
except api.BackendError as error:
    st.error(f'Không tải được cuộc trò chuyện: {error}')
    st.stop()
conversation = view['conversation']


def go_human():
    api.handoff(state.conversation_id)


def render(message):
    sender, kind = message['sender_type'], message.get('kind', 'text')
    if sender == 'end_user':
        with st.chat_message('user'):
            st.markdown(message['content'])
        return
    if sender == 'system':
        if kind == 'emergency':                       # UI-1.4: thẻ đỏ, nổi bật
            st.error('🚨 ' + message['content'])
        elif kind == 'handoff_suggestion':            # UI-1.3
            st.warning(message['content'])
            if conversation['mode'] == 'ai':
                st.button('🧑‍⚕️ Chat với người trực', key=f'h-{message["id"]}', on_click=go_human)
        else:
            st.info(message['content'])
        return
    label = 'assistant' if sender == 'ai' else 'human'
    with st.chat_message(label, avatar='🤖' if sender == 'ai' else '🧑‍⚕️'):
        st.markdown(message['content'])
        if message.get('sources'):                    # UI-1.9: nguồn thu gọn, chỉ ở chế độ AI
            with st.expander('Tài liệu tham khảo'):
                for source in message['sources']:
                    page, end = source.get('page'), source.get('page_end')
                    pages = f'tr. {page}' if not end or end == page else f'tr. {page}-{end}'
                    st.caption(f'{source.get("title") or source.get("source_file")} — {pages}')


for message in view['messages']:
    render(message)

if conversation['mode'] == 'human':
    st.info('🧑‍⚕️ Cuộc trò chuyện đang chờ người trực. Người trực sẽ phản hồi sớm nhất có thể.')
    st.caption('Giai đoạn hiện tại (P1) chưa có giao diện người trực; phần này hoạt động từ P2.')
    st.stop()

st.button('🧑‍⚕️ Chuyển sang người trực', on_click=go_human)      # UI-1.2

question = st.chat_input('Nhập câu hỏi về thuốc...')
if question:
    with st.chat_message('user'):
        st.markdown(question)
    extra = []

    def tokens():
        for event in api.send_message(state.conversation_id, question):
            if event['type'] == 'token':
                yield event['text']
            elif event['type'] in ('message', 'error', 'warning'):
                extra.append(event)

    try:
        with st.chat_message('assistant', avatar='🤖'):
            st.write_stream(tokens())
    except api.BackendError as error:
        st.error(f'Lỗi: {error}')
    for event in extra:
        if event['type'] == 'error':
            st.error(event['detail'])
    st.rerun()      # hiển thị lại theo dữ liệu đã lưu ở backend (thẻ hệ thống, nguồn)
