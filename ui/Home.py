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
    health = api.health()
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

if not health.get('vectors_ready', True):
    # Chỉ mục vector chưa sẵn sàng: vẫn trả lời được nhưng tra cứu chỉ theo từ khoá
    st.warning('Hệ thống tra cứu tài liệu đang được cập nhật; câu trả lời của AI có thể kém đầy đủ '
               'hơn bình thường. Bạn vẫn có thể chọn trò chuyện với người trực.')
    st.caption('Quản trị: ' + ('đang lập chỉ mục, xem tiến độ ở trang Cấu hình model.'
                               if health.get('index_job_running')
                               else 'vào trang Cấu hình model → Chỉ mục tài liệu để dựng hoặc tiếp tục.'))

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
        if sender == 'staff':                         # UI-1.6: tên hiển thị + chức danh
            st.caption(message.get('sender_name') or 'Người trực')
        st.markdown(message['content'])
        if message.get('sources'):                    # UI-1.9: nguồn thu gọn, chỉ ở chế độ AI
            with st.expander('Tài liệu tham khảo'):
                for source in message['sources']:
                    page, end = source.get('page'), source.get('page_end')
                    pages = f'tr. {page}' if not end or end == page else f'tr. {page}-{end}'
                    st.caption(f'{source.get("title") or source.get("source_file")} — {pages}')


if conversation['mode'] == 'human':
    # Tự làm mới để thấy tin người trực (đặc tả 05 mục 3: ≤ 5 giây)
    @st.fragment(run_every=3)
    def live():
        fresh = api.get_conversation(state.conversation_id)
        for message in fresh['messages']:
            render(message)
        status = fresh['conversation']['status']
        if status == 'waiting':
            st.info('🧑‍⚕️ Đang chờ người trực tiếp nhận. Bạn vẫn có thể nhắn thêm thông tin.')
        elif status == 'closed':
            st.caption('Cuộc trò chuyện đã kết thúc. Nhắn tiếp trong 24 giờ để được hỗ trợ thêm.')

    live()
    text = st.chat_input('Nhắn cho người trực...')
    if text:
        for event in api.send_message(state.conversation_id, text):
            if event['type'] == 'conversation':      # quá 24 giờ: chuyển sang cuộc chat mới
                state.conversation_id = event['id']
                st.toast(event['detail'])
            elif event['type'] == 'error':
                st.error(event['detail'])
        st.rerun()
    st.stop()

for message in view['messages']:
    render(message)

st.button('🧑‍⚕️ Chuyển sang người trực', on_click=go_human)      # UI-1.2

question = st.chat_input('Nhập câu hỏi về thuốc...')
if state.get('last_timing'):
    st.caption(state.pop('last_timing'))

STAGES = {'sending': 'Đang gửi câu hỏi', 'classifying': 'Đang phân loại câu hỏi',
          'searching': 'Đang tìm trong tài liệu', 'generating': 'Đang soạn câu trả lời'}


def stream_events(conversation_id, text, inbox):
    """Đọc SSE ở luồng phụ để luồng chính rảnh cập nhật đồng hồ chờ."""
    try:
        for event in api.send_message(conversation_id, text):
            inbox.put(event)
    except api.BackendError as error:
        inbox.put({'type': 'error', 'detail': str(error)})
    except Exception as error:                     # mất kết nối, timeout...
        inbox.put({'type': 'error', 'detail': f'Mất kết nối tới backend: {error}'})
    inbox.put(None)


def loading_html(label, seconds):
    return (f'<div style="display:flex;align-items:center;gap:.6rem;opacity:.8">'
            f'<div class="wait-dot"></div><span>{label}… <b>{seconds:.0f}s</b></span></div>'
            '<style>.wait-dot{width:.8rem;height:.8rem;border-radius:50%;'
            'border:2px solid currentColor;border-top-color:transparent;'
            'animation:wait-spin .8s linear infinite}'
            '@keyframes wait-spin{to{transform:rotate(360deg)}}</style>')


if question:
    import queue
    import threading
    import time

    with st.chat_message('user'):
        st.markdown(question)
    inbox = queue.Queue()
    threading.Thread(target=stream_events, args=(state.conversation_id, question, inbox),
                     daemon=True).start()
    start, first_token, stage = time.monotonic(), None, 'sending'
    text, errors = '', []
    with st.chat_message('assistant', avatar='🤖'):
        body = st.empty()
        timer = st.empty()
        finished = False
        while not finished:
            try:
                event = inbox.get(timeout=0.2)
            except queue.Empty:
                event = 'tick'
            if event is None:
                finished = True
            elif event == 'tick':
                pass
            elif event['type'] == 'status':
                stage = event['stage']
            elif event['type'] == 'token':
                if first_token is None:
                    first_token = time.monotonic() - start
                text += event['text']
            elif event['type'] == 'error':
                errors.append(event['detail'])
            elif event['type'] == 'conversation':
                state.conversation_id = event['id']
            elif event['type'] == 'warning':
                st.toast(event['detail'])
            elapsed = time.monotonic() - start
            if text:
                body.markdown(text + ('' if finished else ' ▌'))
                timer.caption(f'⏱ {elapsed:.0f}s')
            elif not finished:
                body.markdown(loading_html(STAGES.get(stage, 'Đang xử lý'), elapsed),
                              unsafe_allow_html=True)
    for detail in errors:
        st.error(detail)
    total = time.monotonic() - start
    if first_token is not None:
        state.last_timing = f'⏱ Bắt đầu trả lời sau {first_token:.0f}s · hoàn tất sau {total:.0f}s'
    else:
        state.last_timing = f'⏱ Xử lý trong {total:.0f}s'
    if errors:
        st.stop()      # giữ lỗi trên màn hình
    st.rerun()      # hiển thị lại theo dữ liệu đã lưu ở backend (thẻ hệ thống, nguồn)
