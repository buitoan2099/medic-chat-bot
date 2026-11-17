from rag.pdf_parser import (
    find_boilerplate,
    fold,
    is_index_page,
    join_with_pages,
    page_at,
    parse_document,
    strip_accents,
    strip_boilerplate,
)

from tests.conftest import DRUGS


def quiet(_):
    pass


# ---------- chuẩn hoá chuỗi ----------

def test_strip_accents_and_fold():
    assert strip_accents('Chống chỉ định Đặc biệt') == 'chong chi dinh dac biet'
    assert fold('  Tác dụng (ADR)! ') == 'tac dung adr'


# ---------- header / footer ----------

def test_boilerplate_signature_detected_and_running_title_kept(book_pages):
    signatures = find_boilerplate(book_pages)
    assert signatures == {'sach'}

    title, body = strip_boilerplate(book_pages[0], signatures)
    assert title == 'Amoxicilin'
    assert body[0][0] == 'AMOXICILIN'          # header đã bị bỏ
    assert all('SACH' not in line[0] for line in body)


def test_page_number_footer_removed():
    lines = [['Nội dung trang', 9.5, 0.0], ['khác nữa', 9.5, 0.0], ['– 12 –', 9.5, 0.0]]
    _, body = strip_boilerplate(lines, set())
    assert [line[0] for line in body] == ['Nội dung trang', 'khác nữa']


# ---------- trang chỉ mục ----------

def test_index_page_detection(book_pages):
    assert is_index_page(book_pages[-1], total_pages=len(book_pages))
    assert not is_index_page(book_pages[0], total_pages=len(book_pages))


def test_table_with_numbers_is_not_index_page():
    rows = [[f'{150 + i} 50 1,{40 + i}', 9.5, 0.0] for i in range(10)]
    assert not is_index_page(rows, total_pages=500)


# ---------- ghép dòng + vị trí trang ----------

def test_join_lines_keeps_pages_and_hyphenation():
    items = [(3, 'Thuốc ức chế beta-'), (3, 'lactamase được dùng rộng rãi trong lâm sàng.'),
             (4, '- Liều thứ nhất.'), (4, 'Đoạn mới trên trang sau.')]
    text, offsets = join_with_pages(items)
    assert 'beta-lactamase' in text
    assert '\n- Liều thứ nhất.' in text
    assert page_at(offsets, 0, default=None) == 3
    assert page_at(offsets, text.index('Đoạn mới'), default=None) == 4


# ---------- phân tích cấu trúc ----------

def test_parse_document_structure(book_pages):
    doc = parse_document(book_pages, log=quiet)

    assert doc['index_pages'] == [7]
    assert doc['section_types'] == ['Chỉ định', 'Chống chỉ định']
    # Tên chủ đề lấy dạng viết thường chuẩn từ header; tên chạy đầu trang bị
    # đặt ở cuối trang 2 KHÔNG tạo chủ đề trùng.
    assert [t['name'] for t in doc['topics']] == DRUGS

    for node in doc['nodes']:
        assert node['section'] in ('Chỉ định', 'Chống chỉ định')
        topic = doc['topics'][node['topic_id']]
        assert topic['page_start'] <= node['page_start'] <= topic['page_end']
        assert 'SACH' not in node['text']


def test_parenthetical_line_merges_into_heading(book_pages):
    book_pages[2].insert(2, ['(Cephalexin)', 10.0, 1.0])
    doc = parse_document(book_pages, log=quiet)
    names = [t['name'] for t in doc['topics']]
    assert 'Cefalexin (Cephalexin)' in names
    assert '(Cephalexin)' not in names


def test_parse_is_deterministic(book_pages):
    first = parse_document(book_pages, log=quiet)
    second = parse_document(book_pages, log=quiet)
    assert first['nodes'] == second['nodes']
    assert first['topics'] == second['topics']
