"""
Qdrant dùng chung trong backend + rebuild chỉ mục xanh–lục (technical plan X-1, X-3).

- Backend là tiến trình DUY NHẤT mở Qdrant embedded (R1/R2).
- Mọi lời gọi tới client đi qua một khoá: Qdrant embedded ghi SQLite không an toàn
  khi nhiều luồng ghi/đọc đồng thời (đã đo: lỗi "API misuse" và MẤT điểm im lặng).
- Rebuild: dựng collection mới song song, kiểm tra, rồi chuyển con trỏ
  `active_collection`; giữ 1 bản trước để quay lại.
"""

import json
import shutil
import threading
import traceback
from collections import deque
from datetime import datetime

from config import QDRANT_DIR, sidecar_paths
from rag.ingest import IngestCancelled, IngestTarget, run_ingest
from rag.lexical import get_index
from rag.progress import ProgressTracker
from backend.core import LOCAL_TZ, iso, utc_now


class LockedClient:
    """Bọc QdrantClient: mỗi lời gọi phương thức giữ một khoá chung."""

    def __init__(self, client):
        self._client = client
        self._lock = threading.RLock()

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def locked(*args, **kwargs):
            with self._lock:
                return attr(*args, **kwargs)
        return locked


def open_qdrant():
    """Mở Qdrant embedded; báo lỗi rõ nếu tiến trình khác đang giữ (R2)."""

    from rag.rag import open_vector_store
    try:
        return LockedClient(open_vector_store(wait_seconds=3))
    except RuntimeError as error:
        raise RuntimeError(
            'Không mở được Qdrant: có tiến trình khác (app Streamlit cũ, ingest, eval...) '
            f'đang giữ {QDRANT_DIR}. Backend phải là tiến trình duy nhất truy cập Qdrant. '
            f'Chi tiết: {error}') from error


class RebuildJob:
    def __init__(self, target, actor, mode='rebuild'):
        self.target = target
        self.actor = actor
        self.mode = mode                 # rebuild | resume
        self.status = 'running'          # running | complete | failed | cancelled
        self.started_at = iso(utc_now())
        self.finished_at = None
        self.error = None
        self.log = deque(maxlen=300)
        self.cancel_requested = False
        self.progress = ProgressTracker()

    def write(self, line):
        for part in str(line).splitlines() or ['']:
            self.log.append(part)
            self.progress.feed(part)

    def as_dict(self):
        return {'collection': self.target.collection, 'status': self.status, 'mode': self.mode,
                'actor': self.actor, 'started_at': self.started_at,
                'finished_at': self.finished_at, 'error': self.error,
                'done': self.progress.done, 'total': self.progress.total,
                'progress_text': self.progress.text() if self.status == 'running' else None,
                'log_tail': list(self.log)[-40:]}


class IndexManager:
    def __init__(self, client, config_service):
        self.client = client                    # LockedClient hoặc None (chế độ chỉ BM25)
        self.config = config_service
        self.job = None
        self._lock = threading.Lock()

    @property
    def active_collection(self):
        return self.config.settings()['active_collection']

    def has_vectors(self, collection=None):
        """Có tìm bằng vector được không: Qdrant đã mở VÀ collection đã được embed."""

        if self.client is None:
            return False
        return self.client.collection_exists(collection or self.active_collection)

    def resumable(self):
        """
        Collection có lần lập chỉ mục dở dang (ingest_state = in_progress) và không có
        job nào đang chạy: collection đang dùng chưa embed xong, hoặc lần dựng lại bị ngắt.
        """

        if self.job and self.job.status == 'running':
            return []
        found = []
        root = QDRANT_DIR / 'sidecar'
        for state_file in sorted(root.glob('*/ingest_state.json')) if root.exists() else []:
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if state.get('status') != 'in_progress':
                continue
            collection = state_file.parent.name
            found.append({'collection': collection, 'completed_chunks': state.get('completed_chunks', 0),
                          'total_chunks': state.get('total_chunks'),
                          'is_active': collection == self.active_collection})
        return found

    def start_resume(self, actor, collection=None):
        """Embed nốt phần còn thiếu; collection không phải đang dùng thì xong mới chuyển sang."""

        if self.client is None:
            raise RuntimeError('Qdrant chưa mở, không thể lập chỉ mục')
        candidates = {r['collection']: r for r in self.resumable()}
        collection = collection or (self.active_collection if self.active_collection in candidates
                                    else next(iter(candidates), None))
        if collection not in candidates:
            raise RuntimeError('Không có lần lập chỉ mục dở dang nào để tiếp tục')
        with self._lock:
            if self.job and self.job.status == 'running':
                raise RuntimeError(f'Đang lập chỉ mục {self.job.target.collection}')
            self.job = RebuildJob(IngestTarget(collection), actor, mode='resume')
            threading.Thread(target=self._run, args=(self.job,), daemon=True,
                             name='index-resume').start()
            return self.job.as_dict()

    def status(self):
        settings = self.config.settings()
        active = settings['active_collection']
        info = {'active_collection': active,
                'previous_collection': settings.get('previous_collection'),
                'qdrant_open': self.client is not None,
                'points': None, 'chunks': None,
                'job': self.job.as_dict() if self.job else None,
                'resumable': self.resumable()}
        bm25 = get_index(sidecar_paths(active)[1])
        info['chunks'] = len(bm25.chunks) if bm25 else 0
        if self.client is not None and self.client.collection_exists(active):
            info['points'] = self.client.count(collection_name=active, exact=True).count
        return info

    def start_rebuild(self, actor):
        if self.client is None:
            raise RuntimeError('Qdrant chưa mở, không thể lập chỉ mục')
        with self._lock:
            if self.job and self.job.status == 'running':
                raise RuntimeError(f'Đang lập chỉ mục {self.job.target.collection}')
            base = self.active_collection.split('__')[0]
            stamp = datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')
            self.job = RebuildJob(IngestTarget(f'{base}__{stamp}'), actor)
            threading.Thread(target=self._run, args=(self.job,), daemon=True,
                             name='index-rebuild').start()
            return self.job.as_dict()

    def cancel(self):
        if self.job and self.job.status == 'running':
            self.job.cancel_requested = True

    def _run(self, job):
        resume = job.mode == 'resume'
        try:
            stats = run_ingest(self.client, job.target, reset=not resume, resume=resume,
                               log=job.write, should_cancel=lambda: job.cancel_requested)
            points = self.client.count(collection_name=job.target.collection, exact=True).count
            if points != stats['chunks']:
                raise RuntimeError(f'Số điểm {points} ≠ số chunk {stats["chunks"]}')
            if job.target.collection != self.active_collection:
                self._switch_to(job.target.collection, job.actor)
                job.write(f'Đã chuyển sang collection {job.target.collection}')
            job.status = 'complete'
        except IngestCancelled:
            job.status = 'cancelled'
            # Huỷ khi tiếp tục: giữ phần đã embed để lần sau tiếp tục; huỷ khi dựng mới: bỏ
            if not resume:
                self._drop(job.target.collection)
        except BaseException as error:   # ghi lại mọi lỗi, không làm chết backend
            job.status = 'failed'
            job.error = str(error)
            job.write(traceback.format_exc())
        finally:
            job.finished_at = iso(utc_now())

    def _switch_to(self, collection, actor):
        settings = self.config.settings()
        old_active, old_previous = settings['active_collection'], settings.get('previous_collection')
        self.config.update_settings({'active_collection': collection,
                                     'previous_collection': old_active}, actor)
        # Chỉ giữ 1 bản trước để quay lại
        if old_previous and old_previous not in (collection, old_active):
            self._drop(old_previous)

    def rollback(self, actor):
        settings = self.config.settings()
        previous = settings.get('previous_collection')
        if not previous:
            raise RuntimeError('Không có collection trước để quay lại')
        if self.client is not None and not self.client.collection_exists(previous):
            raise RuntimeError(f'Collection {previous} không còn')
        self.config.update_settings({'active_collection': previous,
                                     'previous_collection': settings['active_collection']}, actor)
        return self.config.settings()

    def _drop(self, collection):
        try:
            if self.client is not None and self.client.collection_exists(collection):
                self.client.delete_collection(collection)
        finally:
            shutil.rmtree(sidecar_paths(collection)[0], ignore_errors=True)
