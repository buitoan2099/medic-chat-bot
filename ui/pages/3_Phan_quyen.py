"""Trang cấu hình quyền (đặc tả 02 mục 5): chứng chỉ, cấp chuyên môn, quyền thao tác, lịch sử, mẫu quyền."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ui import api_client as api  # noqa: E402
from ui.staff_login import require_staff  # noqa: E402

st.set_page_config(page_title='Phân quyền', page_icon='🛡️', layout='wide')
st.title('🛡️ Phân quyền người trực')
mgr, me = require_staff('manager', api.Manager)

KINDS = {'bac_si': 'Bác sĩ', 'duoc_si': 'Dược sĩ', 'y_si': 'Y sĩ', 'dieu_duong': 'Điều dưỡng'}
CAPS = {'chat.claim': 'Tự tiếp nhận', 'chat.transfer': 'Chuyển cuộc chat', 'chat.escalate': 'Đẩy cấp',
        'chat.view_all': 'Xem cuộc chat của người khác', 'ai.use_copilot': 'Dùng gợi ý AI',
        'ai.send_unedited': 'Gửi nguyên gợi ý AI'}

staff = mgr.staff()

# ---------- cảnh báo ----------
expiring = [s for s in staff if s['credential_expiring_soon']]
violations = [s for s in staff if s['blocked_30d'] >= 3]
for s in expiring:
    st.warning(f'Chứng chỉ của {s["name"]} hết hạn ngày {s["credential_expires"]}')
for s in violations:
    st.warning(f'{s["name"]}: {s["blocked_30d"]} cảnh báo vượt quyền trong 30 ngày')

# ---------- danh sách ----------
rows = [{'Nhân sự': s['name'], 'Đăng nhập': s['username'], 'Cấp hiệu lực': s['level'],
         'Cấp được cấp': s['effective']['granted_level'], 'Vai trò': ', '.join(s['roles']),
         'Trạng thái': s['presence'], 'Chứng chỉ': KINDS.get(s['credential'], s['credential'] or '—'),
         'Đã xác minh': '✔' if (s['credential_detail'] or {}).get('verified_at') else '',
         'Hết hạn': s['credential_expires'] or '', 'Vượt quyền 30 ngày': s['blocked_30d']}
        for s in staff]
query = st.text_input('Tìm', placeholder='tên hoặc tên đăng nhập')
st.dataframe([r for r in rows if not query or query.lower() in (r['Nhân sự'] + r['Đăng nhập']).lower()],
             hide_index=True, width='stretch')

member = st.selectbox('Chọn nhân sự', staff, format_func=lambda s: f'{s["name"]} ({s["username"]})')
eff = member['effective']
for note in eff['notes']:
    st.info(note)

left, right = st.columns(2)

# ---------- chứng chỉ ----------
with left:
    st.subheader('Chứng chỉ chuyên môn')
    cred = member['credential_detail'] or {}
    with st.form('credential'):
        kind = st.selectbox('Loại', list(KINDS), format_func=KINDS.get,
                            index=list(KINDS).index(cred['kind']) if cred.get('kind') in KINDS else 1)
        number = st.text_input('Số chứng chỉ', cred.get('number', ''))
        issued_by = st.text_input('Nơi cấp', cred.get('issued_by', ''))
        expires = st.text_input('Ngày hết hạn (YYYY-MM-DD, để trống nếu không thời hạn)',
                                cred.get('expires_at') or '')
        verify = st.checkbox('Tôi đã xác minh chứng chỉ (bản gốc/scan)', bool(cred.get('verified_at')))
        if cred.get('verified_at'):
            st.caption(f'Đã xác minh bởi {cred.get("verified_by")} lúc {cred["verified_at"]}')
        if st.form_submit_button('Lưu chứng chỉ'):
            try:
                mgr.credential(member['id'], {'kind': kind, 'number': number, 'issued_by': issued_by,
                                              'expires_at': expires.strip() or None}, verify)
                st.success('Đã lưu.')
                st.rerun()
            except api.BackendError as error:
                st.error(str(error))

# ---------- cấp & quyền ----------
with right:
    st.subheader('Cấp chuyên môn & quyền thao tác')
    with st.form('grants'):
        level = st.selectbox('Cấp chuyên môn', ['C1', 'C2', 'C3'],
                             index=['C1', 'C2', 'C3'].index(eff['granted_level'])
                             if eff['granted_level'] in ('C1', 'C2', 'C3') else 0)
        caps = {k: st.checkbox(label, eff['capabilities'][k]) for k, label in CAPS.items()}
        max_chat = st.number_input('Số cuộc chat tối đa', 1, 20, int(eff['capabilities']['chat.max_concurrent']))
        c1, c2 = st.columns(2)
        start = c1.text_input('Hiệu lực từ (YYYY-MM-DD, trống = ngay)')
        end = c2.text_input('Hiệu lực đến (trống = không thời hạn)')
        reason = st.text_input('Lý do (bắt buộc)')
        if st.form_submit_button('Lưu quyền', type='primary', disabled=False):
            if not reason.strip():
                st.error('Cần ghi lý do.')
            else:
                to_iso = lambda d: f'{d.strip()}T00:00:00+07:00' if d.strip() else None  # noqa: E731
                changes = [('level', level, eff['granted_level']),
                           ('chat.max_concurrent', int(max_chat), eff['capabilities']['chat.max_concurrent'])]
                changes += [(k, v, eff['capabilities'][k]) for k, v in caps.items()]
                errors = []
                for key, value, current in changes:
                    if value == current and not (start.strip() or end.strip()):
                        continue
                    try:
                        mgr.grant(member['id'], key, value, reason, 'settings_page', to_iso(start), to_iso(end))
                    except api.BackendError as error:
                        errors.append(str(error))
                for error in errors:
                    st.error(error)
                if not errors:
                    st.success('Đã lưu.')
                    st.rerun()

    templates = mgr.templates()
    with st.form('template'):
        name = st.selectbox('Mẫu quyền', list(templates),
                            format_func=lambda n: f'{n}: ' + ', '.join(f'{k}={v}' for k, v in templates[n].items()))
        why = st.text_input('Lý do áp mẫu')
        if st.form_submit_button('Áp mẫu'):
            try:
                mgr.apply_template(member['id'], name, why or 'áp mẫu')
                st.rerun()
            except api.BackendError as error:
                st.error(str(error))

# ---------- lịch sử ----------
st.subheader('Lịch sử cấp/thu hồi quyền')
history = mgr.grants(member['id'])
st.dataframe([{'Thời điểm (UTC)': g['created_at'], 'Quyền': g['key'], 'Giá trị': str(g['value']),
               'Hiệu lực từ': g['effective_from'], 'Đến': g.get('effective_to') or '',
               'Lý do': g['reason'], 'Người cấp': g['granted_by'], 'Nguồn': g['source']}
              for g in reversed(history)], hide_index=True, width='stretch')
