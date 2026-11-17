"""
Phân tích cấu trúc PDF theo cách TỔNG QUÁT (không viết riêng cho tài liệu nào).

Cấu trúc được suy ra từ chính tài liệu:
1. Chữ: chỉ lấy chữ nằm trong khổ trang (một số PDF chứa cả chữ của trang
   đối diện ở ngoài khổ giấy -> bị lặp nội dung). Giữ cỡ chữ và độ đậm.
2. Header/footer: dòng đầu/cuối trang có cùng "chữ ký" (từ đầu tiên không
   phải số) lặp lại ở nhiều trang, hoặc chỉ là số trang -> bỏ. Phần còn lại
   của header (vd tên chương/tên mục chạy đầu trang) giữ làm "running title".
3. Tiêu đề: dòng ngắn in đậm hoặc cỡ chữ lớn hơn nội dung. Cấp tiêu đề suy ra
   từ (cỡ chữ, IN HOA). Dòng kết thúc bằng ":" là nhãn trong đoạn, không phải tiêu đề.
4. Tiêu đề lặp lại nhiều lần (vd "Chỉ định", "Mục tiêu") là LOẠI MỤC; tiêu đề
   không lặp lại là CHỦ ĐỀ (tên thuốc, tên chương, tên điều...).
5. Trang mục lục / chỉ mục (đa số dòng dạng "tên ..., số trang") không đưa vào
   nội dung (toàn tên + số trang, gây nhiễu tìm kiếm).
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from pypdf import PdfReader


CACHE_VERSION = 'v3'


# ============================================================
# 1. CHUẨN HOÁ CHUỖI
# ============================================================

def nfc(text):
    return unicodedata.normalize('NFC', text or '')


def strip_accents(text):
    """'Chống chỉ định' -> 'chong chi dinh' (dùng để so khớp không dấu)."""

    text = nfc(text).replace('đ', 'd').replace('Đ', 'D')
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    return text.lower()


def fold(text):
    """Khoá so khớp: bỏ dấu, chữ thường, bỏ ký tự không phải chữ/số."""

    return re.sub(r'[^0-9a-z]+', ' ', strip_accents(text)).strip()


def _clean(text):
    text = nfc(text).replace('\t', ' ').replace(' ', ' ').replace('Ð', 'Đ')
    return re.sub(r' {2,}', ' ', text).strip()


def _upper_ratio(text):
    core = re.sub(r'\([^)]*\)?', '', text)  # phần trong ngoặc được phép viết thường
    letters = [c for c in core if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


# ============================================================
# 2. TRÍCH XUẤT DÒNG KÈM ĐỊNH DẠNG (CÓ CACHE)
# ============================================================

_BOLD_RE = re.compile(r'bold|black|heavy|semibold|demi|,b\b', re.IGNORECASE)


def _extract_page_lines(page):
    """
    Returns:
        list[list]: mỗi dòng [text, cỡ chữ, tỉ lệ ký tự in đậm]
    """

    width = float(page.mediabox.width)
    lines = []
    current = []  # [(text, size, bold)]

    def flush():
        text = _clean(''.join(t for t, _, _ in current))
        if text:
            weights = Counter()
            bold_chars = total = 0
            for t, size, bold in current:
                n = len(t.strip())
                weights[size] += n
                total += n
                bold_chars += n if bold else 0
            size = weights.most_common(1)[0][0] if weights else 0
            lines.append([text, size, round(bold_chars / total, 2) if total else 0])
        current.clear()

    def visitor(text, cm, tm, font_dict, font_size):
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        if not -5 <= x <= width + 5:
            return
        scale = abs(tm[3] * cm[3]) or abs(tm[0] * cm[0]) or 1
        size = round(float(font_size) * scale * 2) / 2
        font = str((font_dict or {}).get('/BaseFont', '')) if font_dict else ''
        bold = bool(_BOLD_RE.search(font))
        for i, part in enumerate(text.split('\n')):
            if i > 0:
                flush()
            if part:
                current.append((part, size, bold))

    page.extract_text(visitor_text=visitor)
    flush()
    return lines


def extract_pages(pdf_path, cache_dir=None, log=print):
    """
    Trích các dòng của từng trang. Cache theo kích thước + mtime của file.

    Returns:
        list[list[list]]: pages[i] = các dòng [text, size, bold] của trang i+1
    """

    pdf_path = Path(pdf_path)
    stat = pdf_path.stat()
    key = f'{pdf_path.name}|{stat.st_size}|{int(stat.st_mtime)}|{CACHE_VERSION}'
    cache_file = Path(cache_dir) / f'{pdf_path.stem}.lines.json' if cache_dir else None

    if cache_file is not None and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding='utf-8'))
            if cached.get('key') == key:
                log(f'Dùng cache trích xuất: {cache_file.name}')
                return cached['pages']
        except (OSError, ValueError):
            pass

    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(_extract_page_lines(page))
        if index % 200 == 0 or index == total:
            log(f'Đã trích xuất {index}/{total} trang')

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({'key': key, 'pages': pages}, ensure_ascii=False),
                              encoding='utf-8')
    return pages


# ============================================================
# 3. HEADER / FOOTER
# ============================================================

def _signature(text):
    """Từ đầu tiên không phải số (bỏ dấu) — header các trang thường giống nhau ở đây."""

    for token in fold(text).split():
        token = re.sub(r'\d+', '', token)
        if len(token) >= 2:
            return token
    return ''


def _is_page_number(text):
    return bool(re.fullmatch(r'[-–—\s]*(trang\s*)?\d{1,4}[-–—\s]*(/\s*\d{1,4})?', fold(text)))


def find_boilerplate(pages, edge=2, min_ratio=0.25):
    """
    Returns:
        set[str]: các "chữ ký" của header/footer.
    """

    counts = Counter()
    for lines in pages:
        edge_lines = lines[:edge] + lines[-edge:]
        counts.update({_signature(line[0]) for line in edge_lines if len(line[0]) <= 120})
    counts.pop('', None)
    threshold = max(3, int(len(pages) * min_ratio))
    return {sig for sig, n in counts.items() if n >= threshold}


def strip_boilerplate(lines, signatures, edge=2):
    """
    Bỏ header/footer khỏi một trang.

    Returns:
        tuple[str, list]: (running title, các dòng còn lại)
    """

    title = ''
    keep = []
    last = len(lines)
    for i, line in enumerate(lines):
        text = line[0]
        at_edge = i < edge or i >= last - edge
        if at_edge and len(text) <= 120 and (_is_page_number(text)
                                             or _signature(text) in signatures):
            if not title and _signature(text) in signatures:
                # "482 DTQGVN 2Dactinomycin" -> "Dactinomycin"
                rest = re.sub(r'^[\W\d_]*', '', text)
                parts = re.split(r'\d+\s*', rest, maxsplit=1)
                candidate = parts[-1].strip() if len(parts) > 1 else ''
                title = candidate if len(candidate) >= 2 else ''
            continue
        keep.append(line)
    return title, keep


# ============================================================
# 4. TRANG MỤC LỤC / CHỈ MỤC
# ============================================================

_ENTRY_RE = re.compile(r'^(.{2,}?)[\s,.…·]+(\d{1,4})\s*$')


def is_index_page(lines, total_pages, min_ratio=0.5):
    """Trang mà đa số dòng có dạng 'tên ..., số trang' (mục lục, chỉ mục cuối sách)."""

    if len(lines) < 8:
        return False
    hits = 0
    for line in lines:
        match = _ENTRY_RE.match(line[0])
        if match and 0 < int(match.group(2)) <= total_pages \
                and sum(c.isalpha() for c in match.group(1)) >= 3:
            hits += 1
    return hits / len(lines) >= min_ratio


# ============================================================
# 5. GHÉP DÒNG THÀNH ĐOẠN
# ============================================================

_PARA_END_RE = re.compile(r'[.:;!?)]$')


def join_with_pages(items):
    """
    Nối các dòng bị ngắt cứng thành đoạn văn.

    Args:
        items: [(trang, text)]
    Returns:
        tuple[str, list[(offset, trang)]]
    """

    paragraphs = []
    lengths = sorted(len(t) for _, t in items)
    typical = lengths[len(lengths) * 3 // 4] if lengths else 60

    previous_line = ''
    for _, line in items:
        if not paragraphs:
            paragraphs.append(line)
        else:
            prev = paragraphs[-1]
            # Dòng trước ngắn và kết thúc bằng dấu câu -> hết đoạn
            if (line.startswith(('- ', '+ ', '• ', '* ', '– '))
                    or (_PARA_END_RE.search(prev) and len(previous_line) < typical * 0.9)):
                paragraphs.append(line)
            elif re.search(r'[^\W\d_]-$', prev):
                paragraphs[-1] = prev + line  # từ bị ngắt bằng gạch nối
            else:
                paragraphs[-1] = prev + ' ' + line
        previous_line = line

    text = '\n'.join(paragraphs)
    offsets = []
    cursor = 0
    for page_no, line in items:
        at = text.find(line, cursor)
        if at < 0:
            continue
        if not offsets or offsets[-1][1] != page_no:
            offsets.append((at, page_no))
        cursor = at + len(line)
    return text, offsets


def page_at(offsets, position, default):
    page = default
    for at, page_no in offsets:
        if at > position:
            break
        page = page_no
    return page


# ============================================================
# 6. TIÊU ĐỀ & CÂY CẤU TRÚC
# ============================================================

def _body_size(pages):
    weights = Counter()
    for lines in pages:
        for text, size, _ in lines:
            weights[size] += len(text)
    return weights.most_common(1)[0][0] if weights else 0


def _heading_style(line, body_size):
    """Kiểu tiêu đề (cỡ chữ, in hoa) hoặc None nếu là dòng nội dung."""

    text, size, bold = line
    letters = sum(c.isalpha() for c in text)
    if not 2 <= len(text) <= 150 or letters < 2 or letters < len(text) * 0.4:
        return None
    if text.endswith((',', ';', ':')):  # nhãn trong đoạn / câu bị ngắt
        return None
    if bold < 0.85 and size < body_size * 1.12:
        return None
    return (size, _upper_ratio(text) >= 0.8)


_ROMAN_RE = re.compile(r'\b(i{1,3}|iv|vi{0,3}|ix|x{1,3})\b')


def _pretty(text, running_titles):
    """Tên hiển thị: ưu tiên dạng viết thường chuẩn ở header trang; IN HOA -> Viết hoa đầu."""

    key = re.sub(r'\s+', '', fold(re.sub(r'\([^)]*\)', '', text)))
    matches = sorted((t for t in running_titles if re.sub(r'\s+', '', fold(t)) == key),
                     key=lambda t: (t.count(' '), t))
    paren = re.findall(r'\([^)]*\)', text)
    if matches and not re.search(r'\b\w \w \w\b', matches[0]):
        return ' '.join([matches[0]] + paren)
    if _upper_ratio(text) >= 0.8:
        # Chỉ đổi chữ thường phần ngoài ngoặc; phần trong ngoặc giữ nguyên như PDF
        core = re.sub(r'\s+', ' ', re.sub(r'\([^)]*\)', ' ', text)).strip()
        lowered = _ROMAN_RE.sub(lambda m: m.group(1).upper(), core.lower())
        return ' '.join([lowered[:1].upper() + lowered[1:]] + paren)
    return text


def parse_document(pages, log=print):
    """
    Phân tích một tài liệu.

    Returns:
        dict:
            nodes: list[dict(path, section, topic_id, page_start, page_end, text, offsets)]
                   — nội dung nằm dưới một tiêu đề
            topics: list[dict(name, page_start, page_end)]
            section_types: list[str] — các tiêu đề lặp lại (loại mục)
            index_pages: list[int]
            stats: dict
    """

    total = len(pages)
    signatures = find_boilerplate(pages)

    cleaned = []
    running_titles = set()
    for lines in pages:
        title, body = strip_boilerplate(lines, signatures)
        if title:
            running_titles.add(_clean(title))
        cleaned.append(body)

    index_pages = [i + 1 for i, lines in enumerate(cleaned) if is_index_page(lines, total)]
    index_set = set(index_pages)

    body_size = _body_size([cleaned[i] for i in range(total) if i + 1 not in index_set])

    # Dòng nội dung + nhận diện tiêu đề, gộp tiêu đề bị ngắt nhiều dòng
    def heading_key(text):
        return re.sub(r'\s+', '', fold(re.sub(r'\([^)]*\)', '', text)))

    # Tiêu đề "kiểu mục" (vd "Thận trọng") xuất hiện rải rác khắp tài liệu, ở
    # nhiều cụm trang cách xa nhau; tên chạy đầu trang chỉ dồn ở vài cụm.
    heading_pages = {}
    for page_no, lines in enumerate(cleaned, start=1):
        if page_no not in index_set:
            for line in lines:
                if _heading_style(line, body_size):
                    heading_pages.setdefault(heading_key(line[0]), []).append(page_no)
    # Kiểu mục = có mặt trên >= 5 trang VÀ (rải ở >= 5 cụm trang cách xa nhau,
    # HOẶC phủ >= 25% số trang). Lưu ý: trong sách mà các chủ đề nối tiếp liên
    # tục (vd Dược thư), tiêu đề mục chỉ tạo 1–3 cụm, nên điều kiện 25% mới là
    # điều kiện bắt được chúng. Tên chạy đầu trang dày đặc tới 25% đã bị loại ở
    # bước header/footer.
    content_pages = max(1, total - len(index_set))
    section_like = set()
    for key, pages_seen in heading_pages.items():
        distinct = len(set(pages_seen))
        clusters = 1 + sum(1 for a, b in zip(pages_seen, pages_seen[1:]) if b - a > 10)
        if distinct >= 5 and (clusters >= 5 or distinct >= 0.25 * content_pages):
            section_like.add(key)

    stream = []  # (trang, text, style | None)
    last_heading_page = {}  # khoá tiêu đề -> trang gần nhất
    for page_no, lines in enumerate(cleaned, start=1):
        if page_no in index_set:
            continue
        for i, line in enumerate(lines):
            style = _heading_style(line, body_size)
            if style:
                key = heading_key(line[0])
                at_edge = i < 3 or i >= len(lines) - 3
                # Tên chạy đầu trang nằm tách dòng (PDF đôi khi đặt ở cuối luồng
                # chữ): tiêu đề ở mép trang, không phải kiểu mục, trùng tiêu đề vừa
                # gặp trong 10 trang -> bỏ. Tiêu đề mục ở đầu trang ("Thận trọng")
                # được giữ.
                if at_edge and key not in section_like \
                        and page_no - last_heading_page.get(key, -99) <= 10:
                    continue
                last_heading_page[key] = page_no
            previous = stream[-1] if stream else None
            same_page_heading = previous and previous[2] and previous[0] == page_no
            if style and re.fullmatch(r'\(.*\)', line[0]):
                # Dòng chỉ gồm "(...)" không mở tiêu đề mới: ghép vào tiêu đề
                # ngay trước ("ACID ACETYLSALICYLIC" + "(Aspirin)"), nếu không
                # thì coi là nội dung (PDF đôi khi đặt dòng này sai thứ tự).
                if same_page_heading:
                    stream[-1] = (page_no, previous[1] + ' ' + line[0], previous[2])
                else:
                    stream.append((page_no, line[0], None))
            elif (style and same_page_heading and previous[2] == style
                    and previous[1].count('\n') < 2):
                stream[-1] = (page_no, previous[1] + '\n' + line[0], style)
            else:
                stream.append((page_no, line[0], style))

    # Cấp tiêu đề: cỡ chữ lớn hơn, IN HOA đứng trước
    styles = sorted({s for _, _, s in stream if s}, key=lambda s: (-s[0], not s[1]))
    level_of = {style: level for level, style in enumerate(styles)}

    # Tiêu đề lặp lại nhiều lần là ứng viên "loại mục"; chỉ giữ những tiêu đề
    # xuất hiện dưới ít nhất 5 tiêu đề cha KHÁC NHAU (vd "Chỉ định" dưới mọi
    # thuốc), loại các tiêu đề chỉ lặp trong một chương.
    heading_counts = Counter(fold(text) for _, text, s in stream if s)
    candidates = {key for key, n in heading_counts.items() if n >= 5}
    parents = {}         # loại mục -> tập tiêu đề cha
    parent_levels = Counter()
    path = []
    for _, text, style in stream:
        if not style:
            continue
        level = level_of[style]
        while path and path[-1][0] >= level:
            path.pop()
        key = fold(text)
        if key in candidates:
            parent = next(((lv, t) for lv, t in reversed(path) if fold(t) not in candidates), None)
            if parent:
                parents.setdefault(key, set()).add(fold(parent[1]))
                parent_levels[parent[0]] += 1
        path.append((level, text))

    repeated = {key for key, ps in parents.items() if len(ps) >= 5}
    # Cấp chủ đề: các cấp tiêu đề thường làm cha của loại mục (vd tên thuốc).
    # Có thể nhiều cấp vì cùng loại tiêu đề đôi khi in khác cỡ chữ.
    total_parents = sum(parent_levels.values())
    topic_levels = {lv for lv, n in parent_levels.items() if n >= 0.05 * total_parents}

    # Các cấp chủ đề là ngang hàng: tên thuốc in cỡ 10 không phải "cha" của
    # tên thuốc in cỡ 9,5 đứng sau nó.
    if topic_levels:
        top = min(topic_levels)
        level_of = {style: (top if lv in topic_levels else lv) for style, lv in level_of.items()}
        topic_levels = {top}

    nodes = []
    path = []  # [(level, text)]
    buffer = []

    def flush():
        if buffer:
            text, offsets = join_with_pages(buffer)
            nodes.append({'path': [t for _, t in path], 'levels': [lv for lv, _ in path],
                          'page_start': buffer[0][0], 'page_end': buffer[-1][0],
                          'text': text, 'offsets': offsets})
        buffer.clear()

    for page_no, text, style in stream:
        if style:
            flush()
            heading = ' '.join(text.split('\n'))
            level = level_of[style]
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, heading))
            # Node rỗng đánh dấu vị trí tiêu đề (để tính phạm vi trang của chủ đề)
            nodes.append({'path': [t for _, t in path], 'levels': [lv for lv, _ in path],
                          'page_start': page_no, 'page_end': page_no, 'text': '',
                          'offsets': [], 'heading': True})
        else:
            buffer.append((page_no, text))
    flush()

    # Chủ đề của một node: tiêu đề ở cấp chủ đề trong đường dẫn; nếu không có
    # (vd phần chương/chuyên đề) thì tiêu đề nông nhất không phải loại mục.
    # Phạm vi trang kéo tới chủ đề kế tiếp.
    topics = []
    for node in nodes:
        levels = node.pop('levels')
        topic_name = next((t for lv, t in reversed(list(zip(levels, node['path'])))
                           if lv in topic_levels and fold(t) not in repeated), None)
        if topic_name is None:
            topic_name = next((t for t in node['path'] if fold(t) not in repeated), None)
        node['section'] = next((t for t in reversed(node['path']) if fold(t) in repeated), None)
        if topic_name is None:
            node['topic_id'] = None
            continue
        if not topics or fold(topics[-1]['raw']) != fold(topic_name):
            topics.append({'raw': topic_name, 'page_start': node['page_start'],
                           'page_end': node['page_end']})
        topics[-1]['page_end'] = max(topics[-1]['page_end'], node['page_end'])
        node['topic_id'] = len(topics) - 1

    for topic in topics:
        topic['name'] = _pretty(topic.pop('raw'), running_titles)

    nodes = [n for n in nodes if not n.get('heading') and n['text'].strip()]

    names_by_key = {}
    for _, text, style in stream:
        if style and fold(text) in repeated:
            names_by_key.setdefault(fold(text), text.replace('\n', ' '))
    section_types = sorted(names_by_key.values())

    stats = {'pages': total, 'body_font_size': body_size, 'heading_levels': len(styles),
             'topic_levels': sorted(topic_levels),
             'topics': len(topics), 'section_types': len(section_types),
             'index_pages': len(index_pages),
             'boilerplate_signatures': sorted(signatures)}
    log(f'Chủ đề: {len(topics)} · Loại mục lặp lại: {len(section_types)} · '
        f'Trang mục lục/chỉ mục (không đưa vào nội dung): {len(index_pages)}')

    return {'nodes': nodes, 'topics': topics, 'section_types': section_types,
            'index_pages': index_pages, 'stats': stats}
