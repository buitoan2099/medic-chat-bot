"""
Tài khoản thử (DEMO_MODE). Tạo sẵn mỗi cấp một tài khoản để chạy thử nhanh các khung;
đăng nhập một chạm không cần mật khẩu, nên CHỈ bật khi thử nghiệm.
"""

import secrets

from backend.domain import AuditLog

DEMO_PREFIX = 'demo_'
DEMO_ACCOUNTS = [
    {'username': 'demo_c1', 'display_name': 'An', 'title': 'Điều dưỡng', 'roles': ['operator'],
     'credential': None, 'level': 'C1'},
    {'username': 'demo_c2', 'display_name': 'Lan', 'title': 'Dược sĩ', 'roles': ['operator'],
     'credential': {'kind': 'duoc_si', 'number': 'DEMO-DS'}, 'level': 'C2'},
    {'username': 'demo_c3', 'display_name': 'Minh', 'title': 'Bác sĩ', 'roles': ['operator'],
     'credential': {'kind': 'bac_si', 'number': 'DEMO-BS'}, 'level': 'C3'},
    {'username': 'demo_quanly', 'display_name': 'Hà', 'title': 'Quản lý',
     'roles': ['manager'], 'credential': None, 'level': 'C1'},
]
ACTOR = 'demo-seed'
REASON = 'Tài khoản thử (DEMO_MODE)'


def ensure_demo_accounts(storage, permissions):
    """Tạo các tài khoản thử còn thiếu (mật khẩu ngẫu nhiên, không ai biết)."""

    for spec in DEMO_ACCOUNTS:
        staff = storage.staff.by_username(spec['username'])
        if staff is None:
            staff = permissions.create_staff(spec['username'], spec['display_name'],
                                             secrets.token_urlsafe(24), ACTOR, spec['title'], spec['roles'])
            if spec['credential']:
                permissions.set_credential(staff.id, spec['credential'], ACTOR, verify=True)
            if spec['level'] != 'C1':
                permissions.grant(staff.id, 'level', spec['level'], ACTOR, REASON)
        else:
            if not staff.active:
                permissions.set_active(staff.id, True, ACTOR)
            if staff.roles != spec['roles']:          # tài khoản tạo từ bản cũ: đồng bộ vai trò
                old = staff.roles
                staff = storage.staff.get(staff.id)
                staff.roles = list(spec['roles'])
                storage.staff.update(staff)
                storage.audit.add(AuditLog(actor=ACTOR, action='staff.roles', target=staff.id,
                                           data={'from': old, 'to': staff.roles}))


def demo_accounts(storage, permissions):
    rows = []
    for spec in DEMO_ACCOUNTS:
        staff = storage.staff.by_username(spec['username'])
        if staff is not None:
            rows.append({'username': staff.username, 'display_name': staff.display_name,
                         'title': staff.title, 'roles': staff.roles,
                         'level': permissions.effective(staff.id)['level']})
    return rows


def demo_login(storage, signer, username):
    if not username.startswith(DEMO_PREFIX) or username not in {a['username'] for a in DEMO_ACCOUNTS}:
        raise ValueError('Không phải tài khoản thử')
    staff = storage.staff.by_username(username)
    if staff is None or not staff.active:
        raise ValueError('Tài khoản thử chưa sẵn sàng')
    storage.audit.add(AuditLog(actor=staff.id, action='demo.login', target=staff.id))
    return staff, signer.sign(staff.id)
