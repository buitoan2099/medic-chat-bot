"""Chế độ chạy thử: tài khoản demo_* chọn nhanh, chỉ khi DEMO_MODE bật."""

import pytest
from fastapi.testclient import TestClient

from backend.llm.gateway import FakeAdapter
from backend.main import build_state, create_app


def app_client(tmp_path, demo):
    adapter = FakeAdapter()
    return TestClient(create_app(lambda: build_state(
        storage_dir=tmp_path / 'storage', adapters={'ollama': adapter}, qdrant=False,
        background='inline', auth_secret='s', demo=demo)))


def test_demo_off_has_no_passwordless_login(tmp_path):
    with app_client(tmp_path, demo=False) as client:
        assert client.get('/api/operator/demo-accounts').status_code == 404
        assert client.post('/api/operator/demo-login', json={'username': 'demo_c2'}).status_code == 404


def test_demo_accounts_seeded_with_levels(tmp_path):
    with app_client(tmp_path, demo=True) as client:
        accounts = {a['username']: a for a in client.get('/api/operator/demo-accounts').json()}
        assert {u: a['level'] for u, a in accounts.items()} == {
            'demo_c1': 'C1', 'demo_c2': 'C2', 'demo_c3': 'C3', 'demo_quanly': 'C1'}
        assert 'manager' in accounts['demo_quanly']['roles']
        token = client.post('/api/operator/demo-login', json={'username': 'demo_c3'}).json()['token']
        me = client.get('/api/operator/me', headers={'Authorization': f'Bearer {token}'}).json()
        assert me['effective']['level'] == 'C3' and me['title'] == 'Bác sĩ'


def test_demo_seed_is_idempotent(tmp_path):
    with app_client(tmp_path, demo=True):
        pass
    with app_client(tmp_path, demo=True) as client:          # khởi động lại: không tạo trùng
        assert len(client.app.state.core.storage.staff.all()) == 4


def test_demo_login_rejects_real_accounts(tmp_path):
    with app_client(tmp_path, demo=True) as client:
        client.app.state.core.permissions.create_staff('lan', 'Lan', 'matkhau123', 'admin')
        assert client.post('/api/operator/demo-login', json={'username': 'lan'}).status_code == 400


def test_demo_manager_is_manager_only_and_cannot_take_chats(tmp_path):
    with app_client(tmp_path, demo=True) as client:
        accounts = {a['username']: a for a in client.get('/api/operator/demo-accounts').json()}
        assert accounts['demo_quanly']['roles'] == ['manager']
        assert all(accounts[u]['roles'] == ['operator'] for u in ('demo_c1', 'demo_c2', 'demo_c3'))
        token = client.post('/api/operator/demo-login', json={'username': 'demo_quanly'}).json()['token']
        h = {'Authorization': f'Bearer {token}'}
        assert client.put('/api/operator/presence', headers=h, json={'status': 'online'}).status_code == 403
        assert client.get('/api/manager/board', headers=h).status_code == 200


def test_old_demo_manager_roles_are_synced(tmp_path):
    with app_client(tmp_path, demo=True) as client:          # giả lập tài khoản tạo từ bản cũ
        storage = client.app.state.core.storage
        staff = storage.staff.by_username('demo_quanly')
        staff.roles = ['operator', 'manager']
        storage.staff.update(staff)
    with app_client(tmp_path, demo=True) as client:
        assert client.app.state.core.storage.staff.by_username('demo_quanly').roles == ['manager']
