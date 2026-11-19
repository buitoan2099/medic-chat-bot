from types import SimpleNamespace

import pytest

import rag.rag as rag
from rag.lexical import BM25Index

from tests.conftest import make_chunk


@pytest.fixture
def index(monkeypatch):
    chunks = [
        make_chunk('n1-c01', 'Amoxicilin › Liều lượng\nNgười lớn uống 500 mg mỗi 8 giờ, '
                   'có thể tăng liều khi nhiễm khuẩn nặng.', 'n1', 2,
                   ['Amoxicilin', 'Liều lượng'], 'Liều lượng'),
        make_chunk('n1-c02', 'Amoxicilin › Liều lượng\ncó thể tăng liều khi nhiễm khuẩn nặng. '
                   'Trẻ em dùng theo cân nặng.', 'n1', 3,
                   ['Amoxicilin', 'Liều lượng'], 'Liều lượng'),
        make_chunk('n2-c01', 'Diclofenac › Chống chỉ định\nLoét dạ dày tiến triển.', 'n2', 5,
                   ['Diclofenac', 'Chống chỉ định'], 'Chống chỉ định'),
    ]
    bm25 = BM25Index(chunks)
    monkeypatch.setattr(rag, 'get_index', lambda *args, **kwargs: bm25)
    return bm25


# ---------- câu hỏi nối tiếp ----------

def test_short_follow_up_uses_previous_question():
    query, carried = rag._with_history('còn trẻ em?', ['Liều amoxicilin cho người lớn'])
    assert carried and query.startswith('Liều amoxicilin')


def test_long_new_question_is_not_merged():
    question = 'Diclofenac có những chống chỉ định gì ở người bị bệnh dạ dày?'
    assert rag._with_history(question, ['câu trước']) == (question, False)


# ---------- truy xuất ----------

def test_retrieve_bm25_only(index):
    result = rag.retrieve('chống chỉ định diclofenac', k=2, use_dense=False)
    assert result['results'][0]['id'] == 'n2-c01'
    assert result['top_score'] is None and result['reason'] is None


def test_low_dense_score_returns_no_results(index, monkeypatch):
    monkeypatch.setattr(rag, 'embed_query', lambda text: [0.1, 0.2])
    point = SimpleNamespace(score=0.2, id='x',
                            payload={'page_content': 'abc', 'metadata': {'chunk_id': 'x'}})
    client = SimpleNamespace(query_points=lambda **kw: SimpleNamespace(points=[point]))

    result = rag.retrieve('câu hỏi không liên quan', client=client)
    assert result['results'] == []
    assert 'ngưỡng' in result['reason']


def test_embedding_failure_falls_back_to_bm25(index, monkeypatch):
    def broken(text):
        raise RuntimeError('Ollama offline')
    monkeypatch.setattr(rag, 'embed_query', broken)

    result = rag.retrieve('chống chỉ định diclofenac', k=1)
    assert result['results'][0]['id'] == 'n2-c01'
    assert 'từ khoá' in result['warning']


# ---------- ngữ cảnh ----------

def test_short_section_is_expanded_and_overlap_removed(index):
    hit = {'id': 'n1-c02', 'text': index.chunks[1]['text'],
           'metadata': index.chunks[1]['metadata'], 'score': 0.8}
    blocks = rag.build_context_blocks([hit])

    assert len(blocks) == 1
    text = blocks[0]['text']
    assert text.startswith('Amoxicilin › Liều lượng\nNgười lớn')
    assert text.count('có thể tăng liều khi nhiễm khuẩn nặng') == 1   # bỏ phần overlap
    assert (blocks[0]['page_start'], blocks[0]['page_end']) == (2, 3)
    assert 'trang 2-3' in rag.format_context(blocks)


def test_same_section_not_repeated(index):
    hits = [{'id': c['id'], 'text': c['text'], 'metadata': c['metadata'], 'score': None}
            for c in index.chunks[:2]]
    assert len(rag.build_context_blocks(hits)) == 1


def test_context_budget_respected(index, monkeypatch):
    monkeypatch.setattr(rag, 'MAX_CONTEXT_CHARS', 50)
    hits = [{'id': c['id'], 'text': c['text'], 'metadata': c['metadata'], 'score': None}
            for c in (index.chunks[0], index.chunks[2])]
    assert len(rag.build_context_blocks(hits)) == 1    # khối đầu luôn có, khối sau vượt ngân sách


def test_bm25_weight_depends_on_accents(index, monkeypatch):
    """Có vector: câu có dấu không dùng BM25 (trọng số 0); câu không dấu có dùng."""
    point = SimpleNamespace(score=0.9, id='v', payload={'page_content': 'Amoxicilin › Liều lượng\nx',
                                                        'metadata': {'chunk_id': 'n1-c01', 'node_id': 'n1'}})
    client = SimpleNamespace(query_points=lambda **kw: SimpleNamespace(points=[point]))
    monkeypatch.setattr(rag, 'embed_query', lambda text: [0.1])
    accented = rag.retrieve('chống chỉ định diclofenac', k=5, client=client, min_score=None)
    assert [r['id'] for r in accented['results']] == ['n1-c01']          # chỉ kết quả vector
    plain = rag.retrieve('chong chi dinh diclofenac', k=5, client=client, min_score=None)
    assert 'n2-c01' in [r['id'] for r in plain['results']]               # BM25 góp thêm
    assert rag.has_accent('Liều') and not rag.has_accent('lieu')
