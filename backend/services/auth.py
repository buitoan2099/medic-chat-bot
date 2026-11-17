"""
Đăng nhập nhân sự (SEC-1): mật khẩu băm scrypt, token ký HMAC có hạn dùng,
khoá tạm sau nhiều lần sai. Không thêm thư viện ngoài.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

TOKEN_TTL_S = 12 * 3600
MAX_FAILURES = 5
LOCKOUT_S = 15 * 60
_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)


class AuthError(RuntimeError):
    pass


def hash_password(password):
    if len(password) < 8:
        raise AuthError('Mật khẩu tối thiểu 8 ký tự')
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, **_SCRYPT)
    return f'scrypt${salt.hex()}${digest.hex()}'


def verify_password(password, stored):
    try:
        scheme, salt_hex, digest_hex = stored.split('$')
    except (ValueError, AttributeError):
        return False
    if scheme != 'scrypt':
        return False
    digest = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class TokenSigner:
    def __init__(self, secret=None):
        self.secret = (secret or secrets.token_urlsafe(32)).encode()

    def sign(self, staff_id, ttl_s=TOKEN_TTL_S):
        payload = _b64(json.dumps({'sid': staff_id, 'exp': int(time.time()) + ttl_s}).encode())
        signature = _b64(hmac.new(self.secret, payload.encode(), hashlib.sha256).digest())
        return f'{payload}.{signature}'

    def verify(self, token):
        try:
            payload, signature = token.split('.')
        except (ValueError, AttributeError):
            raise AuthError('Token không hợp lệ')
        expected = _b64(hmac.new(self.secret, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise AuthError('Token không hợp lệ')
        data = json.loads(_unb64(payload))
        if data['exp'] < time.time():
            raise AuthError('Phiên đăng nhập đã hết hạn')
        return data['sid']


class LoginGuard:
    """Đếm lần đăng nhập sai theo tên đăng nhập; khoá tạm khi vượt ngưỡng."""

    def __init__(self):
        self._failures = {}
        self._lock = threading.Lock()

    def check(self, username):
        with self._lock:
            count, until = self._failures.get(username, (0, 0))
            if until and until > time.time():
                minutes = int((until - time.time()) // 60) + 1
                raise AuthError(f'Tài khoản tạm khoá do đăng nhập sai nhiều lần, thử lại sau {minutes} phút')

    def fail(self, username):
        with self._lock:
            count, _ = self._failures.get(username, (0, 0))
            count += 1
            until = time.time() + LOCKOUT_S if count >= MAX_FAILURES else 0
            self._failures[username] = (0 if until else count, until)

    def success(self, username):
        with self._lock:
            self._failures.pop(username, None)
