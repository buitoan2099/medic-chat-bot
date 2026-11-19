"""Rebuild xanh–lục (technical plan X-3) với Qdrant trong bộ nhớ và ingest giả lập."""

import time

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

import backend.services.index_manager as im
from backend.services.config_service import ConfigService
from backend.services.index_manager import IndexManager, LockedClient
from backend.storage.local import LocalStorage
from rag.ingest import IngestCancelled


@pytest.fixture
def manager(tmp_path, monkeypatch):
    config = ConfigService(LocalStorage(tmp_path / 'storage'))
    config.ensure_seeded()
    config.update_settings({'active_collection': 'sach'}, actor='test')
    client = LockedClient(QdrantClient(':memory:'))
    behaviour = {'points': 3, 'chunks': 3, 'cancel': False}

    def fake_ingest(client, target, reset=False, log=print, should_cancel=None, resume=False, **_):
        behaviour.setdefault('calls', []).append({'collection': target.collection, 'reset': reset,
                                                  'resume': resume})
        if resume and client.collection_exists(target.collection):
            client.upsert(target.collection, [PointStruct(id=i, vector=[1.0, float(i)])
                                              for i in range(behaviour['points'])])
            if behaviour['cancel']:
                raise IngestCancelled('huỷ')
            return {'chunks': behaviour['chunks']}
        if behaviour['cancel'] or (should_cancel and should_cancel()):
            client.create_collection(target.collection,
                                     vectors_config=VectorParams(size=2, distance=Distance.COSINE))
            raise IngestCancelled('huỷ')
        client.create_collection(target.collection,
                                 vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        client.upsert(target.collection, [PointStruct(id=i, vector=[1.0, float(i)])
                                          for i in range(behaviour['points'])])
        log('xong')
        return {'chunks': behaviour['chunks']}

    monkeypatch.setattr(im, 'run_ingest', fake_ingest)
    monkeypatch.setattr(im, 'QDRANT_DIR', tmp_path / 'qdrant')
    return IndexManager(client, config), behaviour


def wait(manager):
    for _ in range(200):
        if manager.job.status != 'running':
            return manager.job.status
        time.sleep(0.01)
    raise AssertionError('rebuild không kết thúc')


def test_rebuild_switches_pointer_and_keeps_one_previous(manager):
    mgr, _ = manager
    mgr.start_rebuild('admin')
    assert wait(mgr) == 'complete'
    first = mgr.active_collection
    assert first.startswith('sach__') and mgr.config.settings()['previous_collection'] == 'sach'

    time.sleep(1.1)                       # tên collection theo giây
    mgr.start_rebuild('admin')
    assert wait(mgr) == 'complete'
    assert mgr.config.settings()['previous_collection'] == first
    assert mgr.client.collection_exists(first)

    time.sleep(1.1)
    mgr.start_rebuild('admin')
    assert wait(mgr) == 'complete'
    assert not mgr.client.collection_exists(first)        # chỉ giữ 1 bản trước


def test_rollback_swaps_active_and_previous(manager):
    mgr, _ = manager
    mgr.client.create_collection('sach', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    mgr.start_rebuild('admin')
    wait(mgr)
    new = mgr.active_collection
    mgr.rollback('admin')
    assert mgr.active_collection == 'sach'
    assert mgr.config.settings()['previous_collection'] == new


def test_failed_count_check_keeps_old_collection(manager):
    mgr, behaviour = manager
    behaviour['chunks'] = 99                               # số điểm ≠ số chunk
    mgr.start_rebuild('admin')
    assert wait(mgr) == 'failed'
    assert mgr.active_collection == 'sach'
    assert 'Số điểm' in mgr.job.error


def test_cancel_drops_partial_collection(manager):
    mgr, behaviour = manager
    behaviour['cancel'] = True
    mgr.start_rebuild('admin')
    assert wait(mgr) == 'cancelled'
    assert mgr.active_collection == 'sach'
    assert not mgr.client.collection_exists(mgr.job.target.collection)


def test_only_one_rebuild_at_a_time(manager):
    mgr, _ = manager
    mgr.job = type('J', (), {'status': 'running', 'target': type('T', (), {'collection': 'x'})()})()
    with pytest.raises(RuntimeError):
        mgr.start_rebuild('admin')


def test_has_vectors_false_when_collection_not_embedded(manager):
    mgr, _ = manager
    assert mgr.has_vectors('chua_embed') is False
    assert IndexManager(None, mgr.config).has_vectors() is False


def _dangling(tmp_path, collection, done=1):
    import json
    folder = tmp_path / 'qdrant' / 'sidecar' / collection
    folder.mkdir(parents=True)
    (folder / 'ingest_state.json').write_text(json.dumps(
        {'status': 'in_progress', 'completed_chunks': done, 'total_chunks': 3}))


def test_resume_active_collection_in_place(manager, tmp_path):
    mgr, behaviour = manager
    mgr.client.create_collection('sach', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    _dangling(tmp_path, 'sach')
    assert [r['collection'] for r in mgr.resumable()] == ['sach']
    mgr.start_resume('admin')
    assert wait(mgr) == 'complete'
    assert behaviour['calls'][-1] == {'collection': 'sach', 'reset': False, 'resume': True}
    assert mgr.active_collection == 'sach'                       # không chuyển collection
    assert mgr.config.settings()['previous_collection'] is None


def test_resume_interrupted_rebuild_switches_when_done(manager, tmp_path):
    mgr, _ = manager
    mgr.client.create_collection('sach__dở', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    _dangling(tmp_path, 'sach__dở')
    mgr.start_resume('admin', 'sach__dở')
    assert wait(mgr) == 'complete'
    assert mgr.active_collection == 'sach__dở'


def test_cancel_during_resume_keeps_progress(manager, tmp_path):
    mgr, behaviour = manager
    mgr.client.create_collection('sach', vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    _dangling(tmp_path, 'sach')
    behaviour['cancel'] = True
    mgr.start_resume('admin')
    assert wait(mgr) == 'cancelled'
    assert mgr.client.collection_exists('sach')                   # không xoá phần đã embed


def test_nothing_to_resume(manager):
    mgr, _ = manager
    with pytest.raises(RuntimeError):
        mgr.start_resume('admin')
