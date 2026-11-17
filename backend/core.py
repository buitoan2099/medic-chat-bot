"""Tiện ích nền: mã định danh sắp xếp theo thời gian, đồng hồ, ngày theo giờ Việt Nam."""

import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo('Asia/Ho_Chi_Minh')

_CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
_id_lock = threading.Lock()
_last = {'ms': -1, 'rand': 0}


def new_id():
    """
    ULID 26 ký tự: 48 bit thời gian (ms) + 80 bit ngẫu nhiên, sắp xếp được theo
    thời gian tạo. Trong cùng một ms, phần ngẫu nhiên tăng dần để giữ thứ tự.
    Dùng nguyên làm khoá chính khi chuyển sang DB.
    """

    with _id_lock:
        ms = int(time.time() * 1000)
        if ms <= _last['ms']:
            ms = _last['ms']
            rand = (_last['rand'] + 1) & ((1 << 80) - 1)
        else:
            rand = int.from_bytes(os.urandom(10), 'big')
        _last['ms'], _last['rand'] = ms, rand

    value = (ms << 80) | rand
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return ''.join(reversed(chars))


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    """ISO 8601 UTC có mili giây, vd 2026-11-18T08:15:30.123Z."""

    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def parse_iso(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


def local_date(dt):
    """Ngày theo giờ Việt Nam ('YYYY-MM-DD'), dùng để chia file và báo cáo."""

    return dt.astimezone(LOCAL_TZ).strftime('%Y-%m-%d')


def id_local_date(record_id):
    """Ngày giờ VN lúc tạo bản ghi, suy từ 48 bit thời gian đầu của ULID."""

    value = 0
    for char in record_id[:10]:
        value = value * 32 + _CROCKFORD.index(char)
    return local_date(datetime.fromtimestamp(value / 1000, tz=timezone.utc))
