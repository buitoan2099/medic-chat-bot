"""Khung 3 – Quản lý (đặc tả 02 mục 3): chat với AG-7, báo cáo nhanh, bảng trạng thái, điều chỉnh nhanh."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.core import LOCAL_TZ, parse_iso  # noqa: E402
from ui import api_client as api  # noqa: E402
from ui.staff_login import require_staff  # noqa: E402

st.set_page_config(page_title='Quản lý', page_icon='📊', layout='wide')
st.title('📊 Quản lý')
mgr, me = require_staff('manager', api.Manager)
state = st.session_state
state.setdefault('mgr_session', None)

URGENCY = {'emergency': '🔴', 'soon': '🟠', 'normal': '⚪'}
REASONS = ['Theo yêu cầu chuyên môn', 'Người mới, cần giám sát', 'Thiếu người trực', 'Khác (ghi bên dưới)']


def minutes(seconds):
    return '—' if seconds is None else f'{int(seconds // 60)}′{int(seconds % 60):02d}″'


# ---------- phiên làm việc ----------

with st.sidebar:
    sessions = mgr.sessions()
    if not sessions or st.button('➕ Phiên mới'):
        state.mgr_session = mgr.new_session()['id']
        st.rerun()
    ids = [s['id'] for s in sessions]
    if state.mgr_session not in ids:
        state.mgr_session = ids[0]
    labels = {s['id']: f'{s["title"]} · {parse_iso(s["updated_at"]).astimezone(LOCAL_TZ):%d/%m %H:%M}'
              for s in sessions}
    state.mgr_session = st.selectbox('Phiên', ids, index=ids.index(state.mgr_session),
                                     format_func=labels.get)


# ---------- điều chỉnh nhanh (popup – đặc tả 02 mục 3.1) ----------

def reason_input(key):
    preset = st.selectbox('Lý do', REASONS, key=f'{key}-preset')
    extra = st.text_input('Ghi chú lý do', key=f'{key}-extra')
    return (extra.strip() if preset.startswith('Khác') else f'{preset}. {extra}'.strip(' .'))


@st.dialog('⚡ Điều chỉnh nhanh', width='large')
def quick_adjust():
    tab_staff, tab_assign, tab_agent = st.tabs(['Người trực', 'Chỉ định', 'Agent'])
    staff = mgr.staff()
    with tab_staff:
        member = st.selectbox('Người trực', staff, format_func=lambda s: f'{s["name"]} · {s["level"]} · {s["presence"]}')
        caps = member['effective']['capabilities']
        level = st.selectbox('Cấp chuyên môn', ['C1', 'C2', 'C3'],
                             index=['C1', 'C2', 'C3'].index(member['effective']['granted_level'])
                             if member['effective']['granted_level'] in ('C1', 'C2', 'C3') else 0)
        unedited = st.toggle('Được gửi nguyên gợi ý AI', caps['ai.send_unedited'])
        max_chat = st.number_input('Số cuộc chat tối đa', 1, 20, int(caps['chat.max_concurrent']))
        reason = reason_input('staff')
        if st.button('Áp dụng', key='apply-staff', disabled=not reason):
            changes = [(k, v) for k, v, cur in (('level', level, member['effective']['granted_level']),
                                                 ('ai.send_unedited', unedited, caps['ai.send_unedited']),
                                                 ('chat.max_concurrent', int(max_chat), caps['chat.max_concurrent']))
                       if v != cur]
            for key, value in changes:
                try:
                    mgr.grant(member['id'], key, value, reason, source='quick_popup')
                except api.BackendError as error:
                    st.error(str(error))           # C2/C3 chưa xác minh -> hướng tới trang Phân quyền
                    if key == 'level':
                        st.info('Xác minh chứng chỉ trên trang **Phân quyền** trước khi nâng cấp.')
                    break
            else:
                st.success(f'Đã áp dụng {len(changes)} thay đổi.')
    with tab_assign:
        board = mgr.board()
        waiting = board['waiting_items']
        if not waiting:
            st.caption('Không có cuộc chat đang chờ.')
        else:
            conv = st.selectbox('Cuộc chat', waiting, format_func=lambda c: (
                f'{URGENCY[c["urgency"]]} {c["required_level"]} · {c["id"][-6:]} · chờ {minutes(c["waited_s"])}'))
            online = [s for s in staff if s['presence'] == 'online']
            target = st.selectbox('Giao cho', online, format_func=lambda s: f'{s["name"]} ({s["level"]})')
            override = st.checkbox('Giao dù người nhận chưa đủ cấp (phải ghi lý do)')
            reason2 = reason_input('assign')
            if st.button('Chỉ định', key='apply-assign', disabled=not (target and reason2)):
                try:
                    mgr.assign(conv['id'], target['id'], reason2, override)
                    st.success('Đã chỉ định.')
                except api.BackendError as error:
                    st.error(str(error))
    with tab_agent:
        agents = mgr.agents()
        copilots = {a: c for a, c in agents.items() if 'copilot' in a or a in ('ag6_guard', 'ag7_manager')}
        agent_id = st.selectbox('Agent', list(copilots), format_func=lambda a: copilots[a]['title'])
        cfg = copilots[agent_id]
        enabled = st.toggle('Bật', cfg['enabled'])
        fallback = st.text_input('Model dự phòng', cfg.get('fallback_model') or '')
        reason3 = reason_input('agent')
        if st.button('Lưu', key='apply-agent', disabled=not reason3):
            mgr.toggle_agent(agent_id, reason3, enabled=enabled,
                             fallback_provider='ollama' if fallback.strip() else None,
                             fallback_model=fallback.strip() or None)
            st.success('Đã lưu.')


# ---------- hiển thị tin & thẻ ----------

def render_card(card, key):
    if card['type'] == 'form':
        st.markdown(card['markdown'])
        st.download_button('⬇️ Tải Markdown', card['markdown'], file_name=f'{card["form"]}-{key}.md',
                           key=f'dl-{key}')
    elif card['type'] == 'table':
        st.markdown(f'**{card["title"]}**')
        rows = [{'Mã': r['code'], 'Người dùng': r['user'], 'Trạng thái': r['status'],
                 'Cấp': r['required_level'], 'Khẩn': URGENCY.get(r['urgency'], ''),
                 'Quá SLA': '⏰' if r['sla_breached'] else ''} for r in card['rows']]
        st.dataframe(rows, hide_index=True, width='stretch')
    elif card['type'] == 'proposal':                       # UI-3.2
        p = card['proposal']
        with st.container(border=True):
            st.markdown(f'**ĐỀ XUẤT THAO TÁC** · {p["summary"]}')
            st.caption(f'Lý do: {p["reason"]} · Trước: {p["before"]}')
            if p['status'] == 'pending':
                c1, c2 = st.columns(2)
                if c1.button('✅ Xác nhận', key=f'ok-{p["id"]}'):
                    result = mgr.decide(p['id'], True)
                    (st.success if result['status'] == 'confirmed' else st.error)(
                        f'{result["status"]}: {result.get("result") or ""}')
                if c2.button('Huỷ', key=f'no-{p["id"]}'):
                    mgr.decide(p['id'], False)
                    st.rerun()
            else:
                st.caption(f'Trạng thái: {p["status"]}')


chat_col, board_col = st.columns([2.2, 1])

with chat_col:
    q1, q2, q3, q4, q5, q6 = st.columns(6)
    for col, (action, label) in zip((q1, q2, q3, q4), [('today', 'Báo cáo hôm nay'), ('week', '7 ngày'),
                                                         ('compare_today', 'So sánh'), ('sla', 'Quá SLA')]):
        if col.button(label, width='stretch'):
            mgr.quick(state.mgr_session, action)
            st.rerun()
    with q5.popover('Hiệu suất…', width='stretch'):
        staff = mgr.staff()
        member = st.selectbox('Người trực', staff, format_func=lambda s: s['name'], key='perf-staff')
        start = st.date_input('Từ ngày', key='perf-from')
        end = st.date_input('Đến ngày', key='perf-to')
        if st.button('Xem F-2'):
            mgr.quick(state.mgr_session, 'operator', {'staff': member['id'], 'from_day': start.isoformat(),
                                                      'to_day': end.isoformat()})
            st.rerun()
    if q6.button('⚡ Điều chỉnh', width='stretch'):
        quick_adjust()

    data = mgr.session(state.mgr_session)
    box = st.container(height=560)
    for message in data['messages']:
        with box.chat_message('user' if message['role'] == 'user' else 'assistant',
                              avatar='🧑‍💼' if message['role'] == 'user' else '📊'):
            for i, card in enumerate(message['cards']):
                render_card(card, f'{message["id"]}-{i}')
            if message['content']:
                st.markdown(message['content'])
    question = st.chat_input('Yêu cầu: tóm tắt cuộc chat, hiệu suất người trực, phân quyền, hỏi tài liệu…')
    if question:
        with st.spinner('AG-7 đang xử lý...'):
            try:
                mgr.ask(state.mgr_session, question)
            except api.BackendError as error:
                st.error(str(error))
        st.rerun()

# ---------- bảng trạng thái (UI-3.3, tự làm mới 10 giây) ----------

with board_col:
    @st.fragment(run_every=10)
    def status_board():
        board = mgr.board()
        st.markdown('#### Bảng trạng thái')
        levels = ' · '.join(f'{k}: {v}' for k, v in sorted(board['on_duty'].items())) or '—'
        st.metric('Đang trực', board['on_duty_total'], help=levels)
        st.caption(f'Theo cấp: {levels}')
        c1, c2 = st.columns(2)
        c1.metric('Đang chờ', board['waiting'])
        c2.metric('Đang xử lý', board['assigned'])
        today = board['today']
        st.caption(f'Hôm nay: {today["conversations"]} cuộc · FRT trung vị {minutes(today["first_response_median_s"])} '
                   f'· chờ trung vị {minutes(today["queue_median_s"])}')
        alerts = [w for w in board['waiting_items'] if w['sla_breached']]
        if alerts or today['blocked_sent_after_confirm'] or today['hard_blocked']:
            st.markdown('**Cảnh báo**')
        for w in alerts:
            st.error(f'#{w["id"][-6:]} chờ {minutes(w["waited_s"])} ({w["required_level"]})')
        if today['blocked_sent_after_confirm']:
            st.warning(f'{today["blocked_sent_after_confirm"]} tin vượt quyền đã gửi sau xác nhận')
        if today['hard_blocked']:
            st.warning(f'{today["hard_blocked"]} tin bị chặn cứng')
        st.markdown('**Đang chờ**')
        for w in board['waiting_items']:
            if st.button(f'{URGENCY[w["urgency"]]} {w["required_level"]} · {w["id"][-6:]} · {minutes(w["waited_s"])}',
                         key=f'view-{w["id"]}'):
                state.mgr_view = w['id']

    status_board()

    if state.get('mgr_view'):                                           # UI-3.6: xem chỉ đọc
        view = mgr.conversation(state.mgr_view)
        with st.expander(f'Cuộc chat #{state.mgr_view[-6:]} (chỉ đọc)', expanded=True):
            for m in view['messages'][-20:]:
                st.caption(f'{m.get("sender_name") or m["sender_type"]}: {m["content"][:300]}')
            if st.button('Đóng xem'):
                state.mgr_view = None
                st.rerun()
