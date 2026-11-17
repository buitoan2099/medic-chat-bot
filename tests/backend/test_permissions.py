from datetime import timedelta

import pytest

from backend.core import iso, local_date, utc_now
from backend.services.auth import AuthError, TokenSigner, hash_password, verify_password
from backend.services.permissions import PermissionError_, PermissionService
from backend.storage.local import LocalStorage

TODAY = local_date(utc_now())


@pytest.fixture
def svc(tmp_path):
    return PermissionService(LocalStorage(tmp_path / 'storage'))


def staff(svc, username='lan', credential=None, verify=False):
    member = svc.create_staff(username, username.title(), 'matkhau123', actor='admin')
    if credential:
        svc.set_credential(member.id, credential, actor='admin', verify=verify)
    return member


# ---------- đăng nhập ----------

def test_password_hash_and_token():
    stored = hash_password('matkhau123')
    assert verify_password('matkhau123', stored) and not verify_password('sai', stored)
    signer = TokenSigner('bi-mat')
    assert signer.verify(signer.sign('s1')) == 's1'
    with pytest.raises(AuthError):
        TokenSigner('khac').verify(signer.sign('s1'))
    with pytest.raises(AuthError):
        signer.verify(signer.sign('s1', ttl_s=-1))


def test_login_lockout_after_failures(svc):
    staff(svc)
    for _ in range(5):
        with pytest.raises(AuthError):
            svc.authenticate('lan', 'sai-mat-khau')
    with pytest.raises(AuthError, match='tạm khoá'):
        svc.authenticate('lan', 'matkhau123')


# ---------- cấp chuyên môn ----------

def test_default_level_c1_and_capability_defaults(svc):
    member = staff(svc)
    eff = svc.effective(member.id)
    assert eff['level'] == 'C1'
    assert eff['capabilities']['ai.send_unedited'] is True
    assert eff['capabilities']['chat.view_all'] is False


def test_cannot_grant_c2_without_verified_credential(svc):
    member = staff(svc, credential={'kind': 'duoc_si'}, verify=False)
    with pytest.raises(PermissionError_):
        svc.grant(member.id, 'level', 'C2', 'manager', 'nâng cấp')


def test_c3_requires_doctor(svc):
    pharmacist = staff(svc, 'lan', {'kind': 'duoc_si'}, verify=True)
    svc.grant(pharmacist.id, 'level', 'C2', 'manager', 'dược sĩ đã xác minh')
    assert svc.effective(pharmacist.id)['level'] == 'C2'
    with pytest.raises(PermissionError_):
        svc.grant(pharmacist.id, 'level', 'C3', 'manager', 'thử')
    doctor = staff(svc, 'minh', {'kind': 'bac_si'}, verify=True)
    svc.grant(doctor.id, 'level', 'C3', 'manager', 'bác sĩ')
    assert svc.effective(doctor.id)['level'] == 'C3'


def test_expired_credential_downgrades_automatically(svc):
    doctor = staff(svc, 'minh', {'kind': 'bac_si', 'expires_at': '2099-01-01'}, verify=True)
    svc.grant(doctor.id, 'level', 'C3', 'manager', 'bác sĩ')
    svc.set_credential(doctor.id, {'kind': 'bac_si', 'expires_at': '2000-01-01'}, 'admin', verify=True)
    eff = svc.effective(doctor.id)
    assert eff['level'] == 'C1' and eff['granted_level'] == 'C3' and eff['notes']


def test_grant_effective_window(svc):
    member = staff(svc)
    later = iso(utc_now() + timedelta(days=1))
    svc.grant(member.id, 'ai.send_unedited', False, 'manager', 'người mới', effective_to=later)
    assert svc.effective(member.id)['capabilities']['ai.send_unedited'] is False
    after = utc_now() + timedelta(days=2)
    assert svc.effective(member.id, at=after)['capabilities']['ai.send_unedited'] is True  # AC-4.6


def test_grant_requires_reason_and_valid_values(svc):
    member = staff(svc)
    with pytest.raises(ValueError):
        svc.grant(member.id, 'chat.max_concurrent', 3, 'manager', '')
    with pytest.raises(ValueError):
        svc.grant(member.id, 'chat.max_concurrent', 99, 'manager', 'x')
    with pytest.raises(ValueError):
        svc.grant(member.id, 'khong.co', True, 'manager', 'x')


def test_presence_requires_level(svc):
    member = staff(svc)
    svc.set_presence(member.id, 'online')
    assert svc.presence(member.id) == 'online'
    svc.set_active(member.id, False, 'admin')
    with pytest.raises(PermissionError_):
        svc.set_presence(member.id, 'online')
