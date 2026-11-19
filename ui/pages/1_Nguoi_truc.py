"""Khung 2 – Người trực ban (đặc tả 02 mục 2)."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.core import LOCAL_TZ, parse_iso  # noqa: E402
from ui import api_client as api  # noqa: E402
from ui.scroll import waiting_indicator  # noqa: E402
from ui.staff_login import logout, require_staff  # noqa: E402

st.set_page_config(page_title='Người trực', page_icon='🧑‍⚕️', layout='wide')
state = st.session_state
state.setdefault('op_token', None)
state.setdefault('op_conv', None)
state.setdefault('composer', '')
state.setdefault('used_suggestion', None)
state.setdefault('pending_check', None)

URGENCY = {'emergency': '🔴 khẩn', 'soon': '🟠 sớm', 'normal': '⚪'}
SENDER = {'end_user': '🙂 Khách', 'ai': '🤖 AI', 'system': 'ℹ️ Hệ thống'}
PROFILE_FIELDS = {'age': 'Tuổi', 'sex': 'Giới', 'pregnant_or_breastfeeding': 'Mang thai / cho con bú',
                  'allergies': 'Dị ứng', 'conditions': 'Bệnh nền',
                  'current_medications': 'Thuốc đang dùng', 'chief_complaint': 'Triệu chứng chính',
                  'onset': 'Khởi phát', 'severity': 'Mức độ'}


def hhmm(iso_text):
    return parse_iso(iso_text).astimezone(LOCAL_TZ).strftime('%H:%M')


def minutes(seconds):
    return f'{int(seconds // 60)}′{int(seconds % 60):02d}″'


# ---------- đăng nhập (dùng chung; có chọn tài khoản thử khi DEMO_MODE) ----------

if not state.get('op_token'):
    st.title('🧑‍⚕️ Người trực')
op, me = require_staff('operator', api.Operator, sidebar=False)
caps = me['effective']['capabilities']

# ---------- thanh bên: thông tin & trạng thái trực (UI-2.9) ----------

with st.sidebar:
    st.subheader(f'{me["title"]} {me["display_name"]}'.strip())
    st.caption(f'Cấp chuyên môn: **{me["effective"]["level"]}**')
    for note in me['effective']['notes']:
        st.warning(note)
    options = ['online', 'away', 'offline']
    labels = {'online': '🟢 Đang trực', 'away': '🟡 Tạm nghỉ', 'offline': '⚫ Rời ca'}
    status = st.radio('Trạng thái', options, index=options.index(me['presence']),
                      format_func=labels.get)
    if status != me['presence']:
        try:
            op.presence(status)
            st.rerun()
        except api.BackendError as error:
            st.error(str(error))
            if st.button('Trả các cuộc chat về hàng chờ và rời ca'):
                op.presence(status, force=True)
                st.rerun()
    if st.button('Đăng xuất'):
        logout('operator')

left, middle, right = st.columns([1.1, 2.2, 1.6])

# ---------- cột trái: hàng chờ + của tôi (UI-2.1, tự làm mới) ----------

with left:
    @st.fragment(run_every=3)
    def lists():
        st.markdown('#### Hàng chờ')
        queue = op.queue()
        if not queue:
            st.caption('Không có cuộc chat nào đang chờ.')
        for item in queue:
            conv = item['conversation']
            sla = ' · ⏰ quá SLA' if item['sla_breached'] else ''
            st.write(f'{URGENCY[conv["urgency"]]} **{conv["required_level"]}** · '
                     f'chờ {minutes(item["waited_s"])}{sla}')
            c1, c2 = st.columns(2)
            if c1.button('Tiếp nhận', key=f'claim-{conv["id"]}', disabled=not caps['chat.claim']):
                try:
                    op.claim(conv['id'])
                    state.op_conv = conv['id']
                    st.rerun()
                except api.BackendError as error:                       # UI-2.2
                    st.toast(str(error).split(': ', 1)[-1])
            if c2.button('Xem', key=f'peek-{conv["id"]}'):
                state.op_conv = conv['id']
                st.rerun()

        mine = op.mine()
        st.markdown(f'#### Của tôi ({len(mine["assigned"])}/{caps["chat.max_concurrent"]})')
        for conv in mine['assigned']:
            label = f'{URGENCY[conv["urgency"]]} {conv["required_level"]} · {conv["id"][-6:]}'
            if st.button(label, key=f'mine-{conv["id"]}', type='primary' if conv['id'] == state.op_conv else 'secondary'):
                state.op_conv = conv['id']
                st.rerun()
        for conv in mine['transfer_offers']:
            offer = conv['pending_transfer']
            st.info(f'Đề nghị chuyển cho bạn: {offer.get("note") or "(không ghi chú)"}')
            c1, c2 = st.columns(2)
            if c1.button('Nhận', key=f'acc-{conv["id"]}'):
                op.respond_transfer(conv['id'], True)
                state.op_conv = conv['id']
                st.rerun()
            if c2.button('Từ chối', key=f'dec-{conv["id"]}'):
                op.respond_transfer(conv['id'], False)
                st.rerun()

    lists()

if not state.op_conv:
    middle.info('Chọn một cuộc chat trong hàng chờ hoặc danh sách "Của tôi".')
    st.stop()

try:
    data = op.view(state.op_conv)
except api.BackendError as error:
    middle.error(str(error))
    state.op_conv = None
    st.stop()
conv = data['conversation']
owner = not data['read_only'] and conv['status'] == 'assigned'

# ---------- cột giữa: cuộc chat (UI-2.3) ----------

with middle:
    st.markdown(f'#### Cuộc chat {conv["id"][-6:]} · {URGENCY[conv["urgency"]]} · '
                f'cần {conv["required_level"]} · {conv["status"]}')
    with st.expander('Hồ sơ ca', expanded=True):
        profile = conv['profile']
        sources = conv.get('profile_sources', {})
        with st.form('profile'):
            cols = st.columns(3)
            values = {}
            for i, (key, label) in enumerate(PROFILE_FIELDS.items()):
                mark = {'staff': ' ✔', 'ai': ' 🤖'}.get(sources.get(key), '')
                values[key] = cols[i % 3].text_input(label + mark, profile.get(key) or '',
                                                     disabled=not owner)
            if profile.get('needs_confirmation'):
                st.warning('Cần xác nhận: ' + '; '.join(profile['needs_confirmation']))
            if conv.get('summary'):
                st.caption(f'Tóm tắt: {conv["summary"]}')
            if st.form_submit_button('Lưu hồ sơ ca', disabled=not owner):
                changed = {k: v for k, v in values.items() if v != (profile.get(k) or '')}
                if changed:
                    op.update_profile(conv['id'], changed)
                    st.rerun()

    @st.fragment(run_every=3)
    def transcript():
        fresh = op.view(state.op_conv)
        box = st.container(height=420, autoscroll=True)
        for message in fresh['messages']:
            who = message.get('sender_name') or SENDER.get(message['sender_type'], '🧑‍⚕️')
            if message['sender_type'] == 'ai':
                who += ' (chế độ AI)'
            style = {'emergency': box.error, 'handoff_suggestion': box.warning}.get(message.get('kind'))
            text = f'**{who}** · {hhmm(message["created_at"])}\n\n{message["content"]}'
            (style or box.markdown)(text)
        events = [e for e in fresh['events'] if e['type'] in
                  ('claimed', 'assigned', 'transferred', 'escalated', 'reopened', 'sla_breached')]
        if events:
            st.caption('Sự kiện: ' + ' · '.join(f'{e["type"]} {hhmm(e["created_at"])}' for e in events))

    transcript()

    if data['read_only']:
        if conv['status'] == 'waiting' and st.button('Tiếp nhận cuộc chat này', type='primary'):
            try:
                op.claim(conv['id'])
                st.rerun()
            except api.BackendError as error:
                st.error(str(error))
        st.stop()
    if not owner:
        st.info('Cuộc chat không còn do bạn phụ trách.')
        st.stop()

    # ---------- soạn & gửi (UI-2.7) ----------
    # Streamlit không cho gán ô soạn tin sau khi đã vẽ: giá trị mới đặt ở composer_next,
    # áp vào đây ở lần chạy kế tiếp, trước khi vẽ ô.
    if 'composer_next' in state:
        state.composer = state.pop('composer_next')
    st.text_area('Soạn tin gửi khách', key='composer', height=110)

    def do_send(text, suggestion_id=None, check_id=None, reason=None):
        try:
            op.send(conv['id'], text, suggestion_id, check_id, reason)
        except api.BackendError as error:
            st.error(str(error).split(': ', 1)[-1])
            return
        state.composer_next, state.used_suggestion, state.pending_check = '', None, None
        st.rerun()

    b1, b2, b3, b4 = st.columns(4)
    if b1.button('📨 Gửi', type='primary', disabled=not state.composer.strip()):
        with st.spinner('Đang gửi…'):
            check = op.check(conv['id'], state.composer, state.used_suggestion)
        if check['hard_block']:
            st.error('⛔ **Không gửi được:** ' + '; '.join(check['issue_texts']))
            if check.get('explanation'):
                st.caption(check['explanation'])
        elif check['needs_confirmation']:
            state.pending_check = check
        else:
            if check['verdict'] == 'warn':
                st.toast('Lưu ý: ' + '; '.join(check['issue_texts']))
            do_send(state.composer, state.used_suggestion, check['id'])

    pending = state.pending_check
    if pending and pending['text'] == state.composer.strip():
        st.warning('**Cần xác nhận trước khi gửi:** ' + ('; '.join(pending['issue_texts'])
                                                       or pending['explanation']))
        st.caption(pending['explanation'])
        reason = st.text_input('Lý do vẫn gửi (bắt buộc)')
        c1, c2 = st.columns(2)
        if c1.button('Vẫn gửi', disabled=not reason.strip()):
            do_send(state.composer, state.used_suggestion, pending['id'], reason)
        if c2.button('Huỷ'):
            state.pending_check = None
            st.rerun()

    with b2.popover('↪️ Chuyển', disabled=not caps['chat.transfer']):
        targets = [s for s in op.online_staff()]
        if targets:
            target = st.selectbox('Người nhận', targets,
                                  format_func=lambda s: f'{s["title"]} {s["display_name"]} ({s["level"]})')
            note = st.text_input('Ghi chú bàn giao')
            if st.button('Gửi đề nghị chuyển'):
                try:
                    op.transfer(conv['id'], target['id'], note)
                    st.success('Đã gửi đề nghị, chờ người nhận chấp nhận.')
                except api.BackendError as error:
                    st.error(str(error))
        else:
            st.caption('Không có người trực nào khác đang online.')
    with b3.popover('⬆️ Đẩy cấp', disabled=not caps['chat.escalate']):
        level = st.selectbox('Cấp cần thiết', ['C2', 'C3'])
        why = st.text_input('Lý do')
        if st.button('Đẩy cấp', disabled=not why.strip()):
            try:
                op.escalate(conv['id'], level, why)
                state.op_conv = None
                st.rerun()
            except api.BackendError as error:
                st.error(str(error))
    if b4.button('✅ Đóng cuộc chat'):
        op.close(conv['id'])
        state.op_conv = None
        st.rerun()

# ---------- cột phải: gợi ý AI (UI-2.4 … 2.6) ----------

with right:
    # Tự làm mới: gợi ý tạo nền mất 1–3 phút, phải tự hiện khi xong (không cần bấm gì)
    @st.fragment(run_every=3)
    def suggestion_panel():
        st.markdown('#### 💡 Gợi ý AI')
        try:
            fresh = op.view(conv['id'])
        except api.BackendError:
            fresh = data
        suggestion = fresh['suggestion']
        pending = fresh.get('suggestion_pending_since')
        customer_msgs = [m for m in fresh['messages'] if m['sender_type'] == 'end_user']
        last_customer = customer_msgs[-1] if customer_msgs else None
        # Gợi ý hiện có là cho tin cũ hơn tin mới nhất của khách -> đang/chưa có gợi ý mới
        stale = bool(suggestion and last_customer
                     and suggestion.get('for_message_id') not in (None, last_customer['id']))
        if pending and caps['ai.use_copilot']:
            waiting_indicator('Đang tạo gợi ý cho tin mới của khách' if stale or suggestion is None
                              else 'Đang tạo lại gợi ý', pending, key=f'sugg-{conv["id"][-8:]}')
            st.caption('Thường mất 1–3 phút; gợi ý tự hiện khi xong.')
        elif stale and caps['ai.use_copilot']:
            st.caption('Tin mới nhất của khách chưa có gợi ý – bấm **🔄 Tạo lại gợi ý** nếu cần.')
        if not caps['ai.use_copilot']:
            st.caption('Bạn chưa được cấp quyền dùng gợi ý AI.')
        elif suggestion is None:
            if not pending:
                st.caption('Chưa có gợi ý (chưa có tin của khách).')
        elif suggestion['status'] == 'error':
            st.error(f'Không tạo được gợi ý: {suggestion["error"][:200]}')
        else:
            holder = (st.expander('🕘 Gợi ý cho tin TRƯỚC của khách (cũ)', expanded=False)
                      if stale else st.container())
            with holder:
                stamp = hhmm(suggestion['created_at'])
                st.caption(f'{suggestion["agent_id"]} · v{suggestion["prompt_version"]} · {stamp}'
                           + (f' · {suggestion["outcome"]}' if suggestion.get('outcome') else ''))
                scope = suggestion.get('scope_check') or {}
                exceeds = scope.get('status') == 'exceeds'
                if exceeds:
                    st.error(f'⛔ Gợi ý vượt quyền cấp {me["effective"]["level"]} → cần '
                             f'{scope.get("suggested_level") or "cấp cao hơn"}: {scope.get("reason")}\n\n'
                             'Không gửi được gợi ý này. Bạn vẫn tự soạn trả lời khách bình thường, '
                             'hoặc dùng **⬆️ Đẩy cấp**.')
                if suggestion.get('red_flags'):
                    st.error('⚠ Dấu hiệu nặng: ' + '; '.join(suggestion['red_flags']))
                st.markdown(suggestion['reply_draft'])
                if suggestion.get('follow_up_questions'):
                    st.caption('Nên hỏi thêm: ' + ' · '.join(suggestion['follow_up_questions']))
                if suggestion.get('monitoring_advice'):
                    st.caption(f'Theo dõi: {suggestion["monitoring_advice"]}')
                if suggestion.get('appointment_needed'):
                    st.caption('📅 Cần hẹn khám trực tiếp')
                with st.expander('Ghi chú nội bộ (không gửi khách)'):
                    st.write(suggestion.get('internal_notes') or '—')
                    st.caption(f'Độ tin cậy: {suggestion.get("confidence")}')
                with st.expander(f'Nguồn tài liệu ({len(suggestion.get("sources", []))})'):
                    for source in suggestion.get('sources', []):
                        st.caption(f'{source.get("title")} — tr. {source.get("page")}')
                        st.text(source.get('excerpt', '')[:300])

                usable = suggestion.get('outcome') is None and owner
                c1, c2, c3 = st.columns(3)
                if caps['ai.send_unedited'] and c1.button('Gửi luôn', disabled=not usable or exceeds,
                                                          help='Gợi ý vượt quyền' if exceeds else None):   # UI-2.5
                    with st.spinner('Đang gửi…'):
                        check = op.check(conv['id'], suggestion['reply_draft'], suggestion['id'])
                    if check['hard_block']:
                        st.error('Tin bị chặn: ' + '; '.join(check['issue_texts']))
                    elif check['needs_confirmation']:
                        # Đưa bản nháp vào ô soạn để hiện khung xác nhận ở cột giữa
                        state.composer_next = suggestion['reply_draft']
                        state.used_suggestion, state.pending_check = suggestion['id'], check
                        st.rerun()
                    else:
                        do_send(suggestion['reply_draft'], suggestion['id'], check['id'])
                if c2.button('Dùng & sửa', disabled=not usable or exceeds,
                             help='Gợi ý vượt quyền' if exceeds else None):
                    state.composer_next = suggestion['reply_draft']
                    state.used_suggestion = suggestion['id']
                    st.rerun()
                if c3.button('Bỏ', disabled=not usable):
                    op.discard(suggestion['id'])
                    st.rerun()

        if owner and caps['ai.use_copilot']:
            with st.form('regen'):
                instruction = st.text_input('Tạo lại với chỉ dẫn (tuỳ chọn)', placeholder='vd: ngắn hơn, hỏi thêm cân nặng')
                if st.form_submit_button('🔄 Tạo lại gợi ý'):
                    op.regenerate(conv['id'], instruction or None)
                    st.toast('Đang tạo gợi ý mới...')
                    st.rerun(scope='fragment')

    suggestion_panel()
