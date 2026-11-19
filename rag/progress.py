"""Theo dõi tiến độ lập chỉ mục: thời gian đã chạy, tốc độ, thời gian còn lại ước tính."""

import re
import time

PROGRESS_RE = re.compile(r'(?:Đã lập chỉ mục\s+|Bỏ qua batch đã lập chỉ mục \()(\d+)/(\d+)(?: chunks|\))')


def human(seconds):
    if seconds is None:
        return '—'
    seconds = int(seconds)
    if seconds < 60:
        return f'{seconds} giây'
    if seconds < 3600:
        return f'{seconds // 60} phút {seconds % 60:02d} giây'
    return f'{seconds // 3600} giờ {seconds % 3600 // 60:02d} phút'


class ProgressTracker:
    """
    Tốc độ chỉ tính từ lần báo tiến độ ĐẦU TIÊN (bỏ qua giai đoạn đọc PDF), và chỉ
    tính các batch thực sự embed (batch "bỏ qua" khi --resume không làm sai tốc độ).
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.done = self.total = 0
        self._rate_start = None          # (thời điểm, số chunk) khi bắt đầu embed thật

    def feed(self, line):
        """Nhận một dòng log; trả True nếu là dòng tiến độ."""

        match = PROGRESS_RE.search(line)
        if not match:
            return False
        done, total = int(match.group(1)), int(match.group(2))
        if 'Bỏ qua' in line:
            self._rate_start = None      # batch có sẵn: chưa tính tốc độ
        elif self._rate_start is None:
            # Mốc = lúc batch embed đầu tiên XONG: không biết batch đó bắt đầu khi nào
            # nên không tính chunk của nó, tránh tốc độ bị thổi phồng.
            self._rate_start = (self.clock(), done)
        self.done, self.total = done, total
        return True

    @property
    def elapsed(self):
        return self.clock() - self.started

    @property
    def rate(self):
        """chunk/giây kể từ khi bắt đầu embed."""

        if self._rate_start is None:
            return None
        seconds = self.clock() - self._rate_start[0]
        chunks = self.done - self._rate_start[1]
        return chunks / seconds if seconds > 0 and chunks > 0 else None

    @property
    def eta(self):
        rate = self.rate
        return (self.total - self.done) / rate if rate and self.total else None

    @property
    def fraction(self):
        return min(self.done / self.total, 1.0) if self.total else 0.0

    def text(self):
        parts = [f'Đã xử lý {self.done:,}/{self.total:,} chunks' if self.total else 'Đang chuẩn bị…',
                 f'Đã chạy {human(self.elapsed)}']
        if self.rate:
            parts.append(f'{self.rate:.1f} chunk/giây')
        if self.eta is not None:
            parts.append(f'Còn khoảng {human(self.eta)}')
        return ' · '.join(parts)
