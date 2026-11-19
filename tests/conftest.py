"""
Dữ liệu giả lập dùng chung: một "cuốn sách" nhỏ có header lặp lại, 6 chủ đề
(tên in đậm IN HOA cỡ 10), 2 loại mục lặp lại (in đậm cỡ 9,5), một trang chỉ mục.
Mỗi dòng có dạng [text, cỡ chữ, tỉ lệ in đậm] như rag.pdf_parser.extract_pages trả về.
"""

import pytest



@pytest.fixture(autouse=True)
def _no_demo_mode(monkeypatch):
    """Test không phụ thuộc DEMO_MODE trong .env của máy (test demo tự truyền demo=True)."""
    import backend.main
    monkeypatch.setattr(backend.main, 'DEMO_MODE', False)


DRUGS = ['Amoxicilin', 'Bisoprolol', 'Cefalexin', 'Diclofenac', 'Erythromycin', 'Furosemid']


def _page(page_no, name, extra_tail=None):
    lines = [
        [f'{page_no} SACH 2{name}', 9.5, 0.4],                     # header (bị loại)
        [name.upper(), 10.0, 1.0],                                  # tên chủ đề
        ['Chỉ định', 9.5, 1.0],                                     # loại mục
        [f'{name} được dùng trong điều trị nhiễm khuẩn thông thường ở', 9.5, 0.0],
        ['người lớn và trẻ em theo hướng dẫn.', 9.5, 0.0],
        ['Chống chỉ định', 9.5, 1.0],
        [f'{name} không dùng cho người quá mẫn với thuốc.', 9.5, 0.0],
        [f'{name} thận trọng ở người suy thận nặng và người cao tuổi.', 9.5, 0.0],
    ]
    if extra_tail:
        lines.append(extra_tail)
    return lines


@pytest.fixture
def book_pages():
    pages = [_page(i + 1, name) for i, name in enumerate(DRUGS)]
    # Trang 2: tên chạy đầu trang của chủ đề trước bị PDF đặt ở CUỐI luồng chữ
    pages[1] = _page(2, DRUGS[1], extra_tail=['AMOXICILIN', 10.0, 1.0])
    # Trang 7: chỉ mục cuối sách (đa số dòng dạng "tên, số trang")
    pages.append([['Mục lục tra cứu', 9.5, 1.0], ['A', 9.5, 1.0]]
                 + [[f'{name}, {i + 1}', 9.5, 0.0] for i, name in enumerate(DRUGS)]
                 + [['Biệt dược A - Amoxicilin, 1', 9.5, 0.0],
                    ['Biệt dược B - Diclofenac, 4', 9.5, 0.0],
                    ['Biệt dược C - Furosemid, 6', 9.5, 0.0],
                    ['Ghi chú cuối trang', 9.5, 0.0]])
    return pages


def make_chunk(chunk_id, text, node_id, page, path=None, section=None):
    return {
        'id': chunk_id,
        'text': text,
        'metadata': {
            'source_file': 'sach.pdf', 'page_number': page, 'page_end': page,
            'topic': (path or [None])[0], 'section': section, 'path': path or [],
            'node_id': node_id, 'chunk_id': chunk_id,
        },
    }
