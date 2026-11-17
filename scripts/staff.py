"""
Quản lý tài khoản nhân sự qua API quản trị (backend phải đang chạy; dùng ADMIN_TOKEN).
Không ghi thẳng vào storage/ vì backend là tiến trình ghi duy nhất.

    python -m scripts.staff list
    python -m scripts.staff create lan "Nguyễn Lan" --title "Dược sĩ" --roles operator
    python -m scripts.staff credential lan --kind duoc_si --number 123 --expires 2030-12-31 --verify
    python -m scripts.staff grant lan level C2 --reason "Đã xác minh chứng chỉ"
    python -m scripts.staff grant lan ai.send_unedited false --reason "Người mới"
    python -m scripts.staff password lan
"""

import argparse
import getpass
import json
import sys

import httpx

from config import ADMIN_TOKEN, BACKEND_URL


def client():
    if not ADMIN_TOKEN:
        sys.exit('Chưa có ADMIN_TOKEN trong .env')
    return httpx.Client(base_url=BACKEND_URL, headers={'X-Admin-Token': ADMIN_TOKEN}, timeout=30)


def call(method, path, body=None):
    with client() as c:
        response = c.request(method, path, json=body)
    if response.status_code >= 400:
        sys.exit(f'Lỗi {response.status_code}: {response.json().get("detail")}')
    return response.json()


def staff_id(username):
    for member in call('GET', '/api/admin/staff'):
        if member['username'] == username.lower():
            return member['id']
    sys.exit(f'Không có nhân sự {username}')


def parse_value(text):
    lowered = text.lower()
    if lowered in ('true', 'false'):
        return lowered == 'true'
    if lowered in ('none', 'null'):
        return None
    return int(text) if text.isdigit() else text


def main():
    parser = argparse.ArgumentParser(description='Quản lý nhân sự')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    create = sub.add_parser('create')
    create.add_argument('username')
    create.add_argument('display_name')
    create.add_argument('--title', default='')
    create.add_argument('--roles', default='operator', help='vd: operator,manager')
    cred = sub.add_parser('credential')
    cred.add_argument('username')
    cred.add_argument('--kind', required=True, help='bac_si | duoc_si | y_si | dieu_duong')
    cred.add_argument('--number', default='')
    cred.add_argument('--issued-by', default='')
    cred.add_argument('--expires', default=None, help='YYYY-MM-DD')
    cred.add_argument('--verify', action='store_true', help='Đánh dấu đã xác minh')
    grant = sub.add_parser('grant')
    grant.add_argument('username')
    grant.add_argument('key', help='level | chat.claim | ai.send_unedited | chat.max_concurrent ...')
    grant.add_argument('value')
    grant.add_argument('--reason', required=True)
    pwd = sub.add_parser('password')
    pwd.add_argument('username')
    args = parser.parse_args()

    if args.cmd == 'list':
        for m in call('GET', '/api/admin/staff'):
            eff = m['effective']
            print(f'{m["username"]:<12} {m["title"] + " " + m["display_name"]:<28} '
                  f'cấp {eff["level"]:<4} vai trò {",".join(m["roles"]):<18} {m["presence"]}')
        return
    if args.cmd == 'create':
        password = getpass.getpass('Mật khẩu (>= 8 ký tự): ')
        result = call('POST', '/api/admin/staff', {
            'username': args.username, 'display_name': args.display_name, 'password': password,
            'title': args.title, 'roles': args.roles.split(',')})
    elif args.cmd == 'credential':
        result = call('PUT', f'/api/admin/staff/{staff_id(args.username)}/credential', {
            'credential': {'kind': args.kind, 'number': args.number, 'issued_by': args.issued_by,
                           'expires_at': args.expires}, 'verify': args.verify})
    elif args.cmd == 'grant':
        result = call('POST', f'/api/admin/staff/{staff_id(args.username)}/grants', {
            'key': args.key, 'value': parse_value(args.value), 'reason': args.reason})
    else:
        result = call('PUT', f'/api/admin/staff/{staff_id(args.username)}/password',
                      {'password': getpass.getpass('Mật khẩu mới: ')})
    print(json.dumps(result, ensure_ascii=False, indent=2)[:1500])


if __name__ == '__main__':
    main()
