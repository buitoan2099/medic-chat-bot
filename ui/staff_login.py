"""
Đăng nhập nhân sự cho các trang khung 2/3. Mỗi khung một phiên riêng:
  - khung 2 (Người trực): vai trò operator, khoá phiên op_token
  - khung 3 (Quản lý, Phân quyền): vai trò manager, khoá phiên mgr_token
Màn đăng nhập chỉ cho chọn/đăng nhập tài khoản đúng vai trò của khung.
"""

import streamlit as st

from ui import api_client as api

PANES = {
    'operator': {'key': 'op_token', 'title': 'Đăng nhập người trực',
                 'wrong': 'Tài khoản này không phải người trực.'},
    'manager': {'key': 'mgr_token', 'title': 'Đăng nhập quản lý',
                'wrong': 'Tài khoản này không phải quản lý.'},
}


def _account_label(account):
    name = f'{account["title"]} {account["display_name"]}'.strip()
    if 'operator' in account['roles']:
        return f'{name} · cấp {account["level"]}'
    return name


def login_screen(role='operator'):
    """Màn đăng nhập của một khung: chọn tài khoản thử (DEMO_MODE) hoặc nhập mật khẩu. Dừng trang."""

    pane = PANES[role]
    state = st.session_state
    st.subheader(pane['title'])

    def enter(token):
        me = api.Operator(token).me()
        if role not in me['roles']:
            st.error(pane['wrong'])
            return
        state[pane['key']] = token
        st.rerun()

    accounts = [a for a in api.demo_accounts() if role in a['roles']]
    if accounts:
        st.caption('🧪 Chế độ chạy thử: chọn một tài khoản có sẵn (không cần mật khẩu).')
        labels = {a['username']: _account_label(a) for a in accounts}
        choice = st.radio('Tài khoản thử', list(labels), format_func=labels.get, key=f'demo-{role}')
        if st.button('Vào', type='primary', key=f'demo-enter-{role}'):
            try:
                enter(api.demo_login(choice)['token'])
            except api.BackendError as error:
                st.error(str(error))
    with st.expander('Đăng nhập bằng tài khoản', expanded=not accounts):
        with st.form(f'login-{role}'):
            username = st.text_input('Tên đăng nhập')
            password = st.text_input('Mật khẩu', type='password')
            if st.form_submit_button('Đăng nhập'):
                try:
                    enter(api.operator_login(username, password)['token'])
                except api.BackendError as error:
                    st.error(str(error))
    st.stop()


def logout(role):
    st.session_state[PANES[role]['key']] = None
    st.rerun()


def require_staff(role='operator', client_class=api.Operator, sidebar=True):
    """Trả về (client, me) của phiên khung `role`; chưa đăng nhập thì hiện màn đăng nhập."""

    key = PANES[role]['key']
    state = st.session_state
    state.setdefault(key, None)
    if not state[key]:
        login_screen(role)
    client = client_class(state[key])
    try:
        me = client.me()
    except api.BackendError:
        state[key] = None
        st.rerun()
    if role not in me['roles']:          # vai trò bị thu hồi khi đang đăng nhập
        state[key] = None
        st.rerun()
    if sidebar:
        sidebar_account(me, role)
    return client, me


def sidebar_account(me, role):
    with st.sidebar:
        st.caption(f'Đăng nhập: {me["title"]} {me["display_name"]}'.strip())
        if st.button('Đăng xuất', key=f'logout-{role}'):
            logout(role)
