from rag.progress import ProgressTracker, human


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_elapsed_ticks_between_progress_lines():
    clock = Clock()
    tracker = ProgressTracker(clock)
    clock.now = 40                                   # đọc PDF 40 giây, chưa có tiến độ
    assert tracker.rate is None and 'Đang chuẩn bị' in tracker.text()
    tracker.feed('Đã lập chỉ mục 32/16160 chunks')
    clock.now = 50
    tracker.feed('Đã lập chỉ mục 352/16160 chunks')  # 320 chunk / 10 giây
    assert tracker.rate == 32.0                       # không tính 40 giây đọc PDF
    clock.now = 55                                    # chưa có dòng mới nhưng đồng hồ vẫn chạy
    assert tracker.elapsed == 55
    assert '55 giây' in tracker.text() and 'Còn khoảng' in tracker.text()


def test_skipped_batches_do_not_inflate_rate():
    clock = Clock()
    tracker = ProgressTracker(clock)
    tracker.feed('Bỏ qua batch đã lập chỉ mục (5000/16160)')
    clock.now = 1
    tracker.feed('Bỏ qua batch đã lập chỉ mục (8000/16160)')
    assert tracker.rate is None                       # resume: batch có sẵn không tính tốc độ
    tracker.feed('Đã lập chỉ mục 8032/16160 chunks')
    clock.now = 11
    tracker.feed('Đã lập chỉ mục 8352/16160 chunks')
    assert tracker.rate == 32.0


def test_human():
    assert human(59) == '59 giây' and human(125) == '2 phút 05 giây' and human(3720) == '1 giờ 02 phút'
