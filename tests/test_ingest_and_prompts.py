import hashlib
import json

import pytest

from config import CHUNKS_FILE, QDRANT_DIR
from provider.prompts import ThinkFilter, clean_response
from rag.ingest import build_chunks, point_id
from rag.pdf_parser import parse_document


def quiet(_):
    pass


# ---------- tạo chunk ----------

def test_build_chunks_header_metadata_and_unique_ids(book_pages):
    chunks = build_chunks('ftest', 'sach.pdf', parse_document(book_pages, log=quiet))

    assert len({c['id'] for c in chunks}) == len(chunks)
    first = chunks[0]
    assert first['text'].startswith('Amoxicilin › Chỉ định\n')
    meta = first['metadata']
    assert meta['topic'] == 'Amoxicilin' and meta['section'] == 'Chỉ định'
    assert meta['page_number'] == 1 and meta['node_id'].startswith('ftest-')


def test_point_id_is_stable():
    assert point_id('ftest-n00001-c01') == point_id('ftest-n00001-c01')
    assert point_id('ftest-n00001-c01') != point_id('ftest-n00001-c02')


# ---------- lọc <think> ----------

@pytest.mark.parametrize('parts, expected', [
    (['<thi', 'nk>nháp</th', 'ink>\n\nXin ', 'chào'], 'Xin chào'),
    (['Xin', ' chào'], 'Xin chào'),
    (['<', 'b>đậm</b>'], '<b>đậm</b>'),
    (['  <think>chưa xong'], ''),
])
def test_think_filter_streaming(parts, expected):
    stream = ThinkFilter()
    assert ''.join(stream.feed(p) for p in parts) + stream.flush() == expected


def test_clean_response():
    assert clean_response('<think>x</think>  Trả lời') == 'Trả lời'


# ---------- hồi quy trên Dược thư thật ----------

CACHE = QDRANT_DIR / 'cache' / 'duoc-thu-quoc-gia-viet-nam-2018.lines.json'


@pytest.mark.corpus
@pytest.mark.skipif(not CACHE.exists(), reason='Thiếu cache trích xuất PDF (chạy rag.ingest --dry-run trước)')
def test_corpus_parse_regression():
    pages = json.loads(CACHE.read_text(encoding='utf-8'))['pages']
    doc = parse_document(pages, log=quiet)
    chunks = build_chunks(_file_tag('duoc-thu-quoc-gia-viet-nam-2018.pdf'),
                          'duoc-thu-quoc-gia-viet-nam-2018.pdf', doc)

    stats = doc['stats']
    assert stats['boilerplate_signatures'] == ['dtqgvn']
    assert stats['topics'] == 742
    assert stats['section_types'] == 22
    assert stats['index_pages'] == 137
    assert len(chunks) == 16160

    names = {t['name'] for t in doc['topics']}
    for expected in ('Paracetamol (Acetaminophen)', 'Acid acetylsalicylic (Aspirin)', 'Ondansetron',
                     'Amoxicilin và kali clavulanat'):
        assert expected in names


@pytest.mark.corpus
@pytest.mark.skipif(not (CACHE.exists() and CHUNKS_FILE.exists()),
                    reason='Chưa có cache trích xuất hoặc chunks.jsonl')
def test_chunks_file_matches_current_parser():
    """chunks.jsonl đang dùng phải khớp kết quả parser hiện tại (không bị cũ so với code)."""
    pages = json.loads(CACHE.read_text(encoding='utf-8'))['pages']
    expected = build_chunks(_file_tag('duoc-thu-quoc-gia-viet-nam-2018.pdf'),
                            'duoc-thu-quoc-gia-viet-nam-2018.pdf',
                            parse_document(pages, log=quiet))
    current = [json.loads(line) for line in CHUNKS_FILE.read_text(encoding='utf-8').splitlines()]
    assert [c['id'] for c in current] == [c['id'] for c in expected]
    assert [c['text'] for c in current] == [c['text'] for c in expected], \
        'chunks.jsonl đã cũ: chạy lại python -m rag.ingest --dry-run'


def _file_tag(name):
    return 'f' + hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]
