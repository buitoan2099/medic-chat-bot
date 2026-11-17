"""
Nhân sự & phân quyền (đặc tả 01 mục 2, đặc tả 04 mục 2.2).

- Cấp chuyên môn C1/C2/C3 lũy tiến. C2/C3 chỉ có hiệu lực khi có chứng chỉ ĐÃ
  XÁC MINH và CÒN HẠN; C3 phải là bác sĩ. Hết hạn -> tự hạ về cấp hợp lệ cao nhất.
- Quyền thao tác (capability) cấu hình riêng, có mặc định.
- Mỗi lần cấp/thu hồi là một PermissionGrant (chỉ thêm), có hiệu lực từ/đến.
"""

from backend.core import iso, local_date, parse_iso, utc_now
from backend.domain import (
    LEVEL_ORDER,
    AuditLog,
    Credential,
    Level,
    PermissionGrant,
    Staff,
    StaffPresence,
)
from backend.services.auth import AuthError, LoginGuard, hash_password, verify_password

LEVELS = ['none', 'C1', 'C2', 'C3']
CAPABILITY_DEFAULTS = {
    'chat.claim': True,
    'chat.transfer': True,
    'chat.escalate': True,
    'chat.view_all': False,
    'ai.use_copilot': True,
    'ai.send_unedited': True,
    'chat.max_concurrent': 5,
}
ROLES = {'operator', 'manager', 'admin'}
DOCTOR = 'bac_si'


class PermissionError_(RuntimeError):
    """Không đủ quyền (tránh trùng tên PermissionError có sẵn)."""


def level_value(level):
    return LEVEL_ORDER[Level(level)]


def credential_valid(credential, today=None):
    if credential is None or not credential.verified_at:
        return False
    today = today or local_date(utc_now())
    return credential.expires_at is None or credential.expires_at >= today


def max_level_allowed(staff, today=None):
    """Cấp cao nhất nhân sự ĐƯỢC PHÉP có theo chứng chỉ hiện tại."""

    if not staff.active:
        return 'none'
    if credential_valid(staff.credential, today):
        return 'C3' if staff.credential.kind == DOCTOR else 'C2'
    return 'C1'


class PermissionService:
    def __init__(self, storage):
        self.storage = storage
        self.login_guard = LoginGuard()

    # ---------- nhân sự ----------

    def create_staff(self, username, display_name, password, actor, title='', roles=None,
                     credential=None):
        roles = roles or ['operator']
        unknown = set(roles) - ROLES
        if unknown:
            raise ValueError(f'Vai trò không hợp lệ: {", ".join(sorted(unknown))}')
        staff = Staff(username=username.strip().lower(), display_name=display_name, title=title,
                      roles=roles, password_hash=hash_password(password),
                      credential=Credential.model_validate(credential) if credential else None)
        self.storage.staff.add(staff)
        self._audit(actor, 'staff.create', staff.id, {'username': staff.username, 'roles': roles})
        return staff

    def authenticate(self, username, password):
        username = (username or '').strip().lower()
        self.login_guard.check(username)
        staff = self.storage.staff.by_username(username)
        if staff is None or not staff.active or not verify_password(password, staff.password_hash):
            self.login_guard.fail(username)
            raise AuthError('Sai tên đăng nhập hoặc mật khẩu')
        self.login_guard.success(username)
        return staff

    def set_password(self, staff_id, password, actor):
        staff = self.storage.staff.get(staff_id)
        staff.password_hash = hash_password(password)
        self.storage.staff.update(staff)
        self._audit(actor, 'staff.password', staff_id, {})

    def set_credential(self, staff_id, credential, actor, verify=False):
        """Ghi chứng chỉ; verify=True đánh dấu đã xác minh bởi actor."""

        staff = self.storage.staff.get(staff_id)
        cred = Credential.model_validate(credential)
        if verify:
            cred.verified_by, cred.verified_at = actor, iso(utc_now())
        staff.credential = cred
        self.storage.staff.update(staff)
        self._audit(actor, 'staff.credential', staff_id,
                    {'kind': cred.kind, 'expires_at': cred.expires_at, 'verified': verify})
        return staff

    def set_active(self, staff_id, active, actor):
        staff = self.storage.staff.get(staff_id)
        staff.active = active
        self.storage.staff.update(staff)
        self._audit(actor, 'staff.active', staff_id, {'active': active})

    # ---------- quyền ----------

    def _active_grants(self, staff_id, at):
        latest = {}
        for grant in self.storage.permissions.for_staff(staff_id):
            if parse_iso(grant.effective_from) > at:
                continue
            if grant.effective_to and parse_iso(grant.effective_to) <= at:
                continue
            latest[grant.key] = grant        # bản sau ghi đè bản trước
        return latest

    def effective(self, staff_id, at=None):
        """
        Quyền hiện hành.

        Returns:
            dict: level, granted_level, capabilities, notes
        """

        at = at or utc_now()
        staff = self.storage.staff.get(staff_id)
        grants = self._active_grants(staff_id, at)
        granted = grants['level'].value if 'level' in grants and grants['level'].value else 'C1'
        allowed = max_level_allowed(staff, local_date(at))
        level = granted if level_value(granted) <= level_value(allowed) else allowed
        notes = []
        if level != granted:
            notes.append(f'Được cấp {granted} nhưng chứng chỉ chỉ cho phép {allowed} '
                         '(chưa xác minh hoặc đã hết hạn)')
        capabilities = dict(CAPABILITY_DEFAULTS)
        for key in CAPABILITY_DEFAULTS:
            if key in grants and grants[key].value is not None:
                capabilities[key] = grants[key].value
        return {'level': level, 'granted_level': granted, 'capabilities': capabilities,
                'notes': notes, 'roles': staff.roles}

    def grant(self, staff_id, key, value, actor, reason, effective_from=None, effective_to=None,
              source='admin_api'):
        if not reason or not reason.strip():
            raise ValueError('Cần ghi lý do (đặc tả 02 mục 3.1)')
        staff = self.storage.staff.get(staff_id)
        if key == 'level':
            if value not in LEVELS:
                raise ValueError(f'Cấp không hợp lệ: {value}')
            allowed = max_level_allowed(staff)
            if level_value(value) > level_value(allowed):
                raise PermissionError_(
                    f'Không thể cấp {value}: chứng chỉ của {staff.display_name} chỉ cho phép '
                    f'{allowed}. Cần xác minh chứng chỉ trên trang phân quyền trước.')
            kind = 'level'
        elif key in CAPABILITY_DEFAULTS:
            if key == 'chat.max_concurrent':
                value = int(value)
                if not 1 <= value <= 20:
                    raise ValueError('Số cuộc chat tối đa phải trong 1–20')
            elif value is not None and not isinstance(value, bool):
                raise ValueError(f'{key} nhận true/false')
            kind = 'capability'
        else:
            raise ValueError(f'Quyền không tồn tại: {key}')
        grant = PermissionGrant(staff_id=staff_id, kind=kind, key=key, value=value, reason=reason,
                                granted_by=actor, source=source,
                                effective_from=effective_from or iso(utc_now()),
                                effective_to=effective_to)
        self.storage.permissions.add(grant)
        self._audit(actor, 'permission.grant', staff_id, {'key': key, 'value': value,
                                                          'reason': reason, 'source': source})
        return grant

    def require(self, staff_id, capability):
        if not self.effective(staff_id)['capabilities'].get(capability):
            raise PermissionError_(f'Không có quyền {capability}')

    def require_role(self, staff_id, role):
        if role not in self.storage.staff.get(staff_id).roles:
            raise PermissionError_(f'Cần vai trò {role}')

    # ---------- trạng thái trực ----------

    def presence(self, staff_id):
        current = self.storage.presence.current().get(staff_id)
        return current.status if current else 'offline'

    def set_presence(self, staff_id, status):
        if status not in ('online', 'away', 'offline'):
            raise ValueError('Trạng thái phải là online | away | offline')
        if status == 'online' and self.effective(staff_id)['level'] == 'none':
            raise PermissionError_('Tài khoản chưa có cấp chuyên môn để trực')
        self.storage.presence.add(StaffPresence(staff_id=staff_id, status=status))

    def _audit(self, actor, action, target, data):
        self.storage.audit.add(AuditLog(actor=actor, action=action, target=target, data=data))
