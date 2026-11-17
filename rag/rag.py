"""
Truy xuất và hỏi đáp (RAG) trên các tài liệu đã lập chỉ mục.

Quy trình truy xuất (hybrid, không phụ thuộc loại tài liệu):
1. Câu hỏi nối tiếp ngắn ("còn liều cho trẻ em?") được ghép thêm câu hỏi
   trước khi tìm kiếm.
2. Lấy ứng viên từ tìm kiếm vector (Qdrant) và từ khoá (BM25).
3. Gộp bằng Reciprocal Rank Fusion.
4. Độ tương đồng vector thấp hơn ngưỡng -> không gọi LLM.
5. Mở rộng ngữ cảnh: nếu cả mục chứa đoạn tìm được ngắn thì đưa nguyên mục.
"""

import re
import threading
import time

from qdrant_client import QdrantClient

from config import CANDIDATE_K, COLLECTION_NAME, MIN_SCORE, QDRANT_DIR, TOP_K, sidecar_paths
from provider.llm import call_generation_api, stream_generation_api
from rag.embeddings import embed_query
from rag.lexical import get_index
from rag.pdf_parser import fold


# ============================================================
# 1. QDRANT CONNECTION - MỘT CLIENT DÙNG CHUNG
# ============================================================
# Qdrant local chỉ cho phép MỘT process mở thư mục lưu trữ, và mỗi lần mở
# client phải nạp toàn bộ vector từ đĩa (vài giây). Vì vậy giữ một client
# dùng chung trong process; chỉ đóng khi cần nhường cho tiến trình ingest.

_LOCK_MARKER = 'already accessed by another instance'

_store_lock = threading.RLock()
_store = {'client': None, 'paused': False}


def open_vector_store(wait_seconds=15, poll_seconds=0.5):
    """
    Mở một client Qdrant MỚI (caller tự close). Dùng cho script/eval;
    trong app hãy dùng get_vector_store().
    """

    if not QDRANT_DIR.exists():
        raise FileNotFoundError(f'Chưa có Qdrant index tại {QDRANT_DIR}. '
                                'Hãy chạy: python -m rag.ingest --reset')

    deadline = time.monotonic() + wait_seconds

    while True:
        try:
            return QdrantClient(path=str(QDRANT_DIR))
        except RuntimeError as error:
            if _LOCK_MARKER not in str(error):
                raise
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    'Qdrant local đang được một tiến trình khác sử dụng '
                    '(chỉ cho phép 1 process). Hãy tắt app/script kia rồi thử lại.'
                ) from error
            time.sleep(poll_seconds)


def get_vector_store(wait_seconds=15):
    """Client dùng chung trong process (mở lần đầu, giữ cho các lần sau)."""

    with _store_lock:
        if _store['paused']:
            raise RuntimeError('Đang lập chỉ mục lại, vui lòng chờ hoàn tất.')
        if _store['client'] is None:
            _store['client'] = open_vector_store(wait_seconds=wait_seconds)
        return _store['client']


def close_vector_store(pause=False):
    """Đóng client dùng chung. pause=True: chặn mở lại (khi đang ingest)."""

    with _store_lock:
        _store['paused'] = pause
        if _store['client'] is not None:
            try:
                _store['client'].close()
            finally:
                _store['client'] = None


def resume_vector_store():
    with _store_lock:
        _store['paused'] = False


# ============================================================
# 2. RETRIEVAL - TRUY XUẤT KẾT HỢP
# ============================================================

RRF_K = 60
# Câu hỏi ngắn hơn ngần này từ được coi là có thể là câu hỏi nối tiếp
FOLLOW_UP_MAX_WORDS = 6
_FOLLOW_UP_RE = re.compile(r'^(con|vay|the|no|cai nay|cai do|neu|con neu)\b')


def _with_history(question, history):
    """
    Câu hỏi nối tiếp (ngắn hoặc bắt đầu bằng "còn", "vậy"...) được ghép câu
    hỏi trước để tìm kiếm có đủ ngữ cảnh. Câu trả lời của LLM vẫn dựa trên
    câu hỏi gốc.
    """

    if not history:
        return question, False
    text = fold(question)
    if len(text.split()) <= FOLLOW_UP_MAX_WORDS or _FOLLOW_UP_RE.match(text):
        return f'{history[-1]} {question}', True
    return question, False


def _bm25(collection):
    return get_index(sidecar_paths(collection or COLLECTION_NAME)[1])


def retrieve(question, k=TOP_K, history=None, client=None, use_dense=True, collection=None,
             query_override=None, min_score=MIN_SCORE, candidate_k=CANDIDATE_K):
    """
    Tìm các đoạn liên quan đến câu hỏi.

    Args:
        question (str): Câu hỏi.
        k (int): Số đoạn trả về.
        history (list[str] | None): Các câu hỏi trước của người dùng.
        client: QdrantClient (mặc định dùng client chung).
        use_dense (bool): False -> chỉ dùng BM25 (không cần Ollama).
        collection (str | None): collection cần tìm (mặc định COLLECTION_NAME).
        query_override (str | None): truy vấn dựng sẵn (vd câu hỏi + hồ sơ ca);
            khi có thì bỏ qua cơ chế ghép câu hỏi trước.
        min_score (float | None): ngưỡng cosine; None = không áp ngưỡng.

    Returns:
        dict: results (list), query (str), carried (bool),
              top_score (float | None), reason (str | None), warning (str | None)
    """

    collection = collection or COLLECTION_NAME
    bm25 = _bm25(collection)
    if query_override:
        query, carried = query_override, False
    else:
        query, carried = _with_history(question, history)

    warning = None
    vector = None
    if use_dense:
        try:
            vector = embed_query(query)
        except RuntimeError as error:
            # Ollama (embedding) mất kết nối: vẫn tìm được bằng BM25
            if bm25 is None:
                raise
            warning = f'Không tạo được embedding, chỉ tìm theo từ khoá. ({error})'

    candidates = {}  # chunk id -> {'text', 'metadata', 'rrf', 'dense'}

    def add(rank, chunk_id, text, metadata, dense=None):
        entry = candidates.setdefault(chunk_id, {
            'text': text, 'metadata': metadata, 'rrf': 0.0, 'dense': None,
        })
        entry['rrf'] += 1.0 / (RRF_K + rank)
        if dense is not None:
            entry['dense'] = max(entry['dense'] or 0.0, dense)

    top_score = None
    if vector is not None:
        client = client or get_vector_store()
        points = client.query_points(collection_name=collection, query=vector,
                                     limit=candidate_k, with_payload=True).points
        for rank, point in enumerate(points, start=1):
            payload = point.payload or {}
            metadata = dict(payload.get('metadata', {}))
            add(rank, metadata.get('chunk_id') or str(point.id),
                str(payload.get('page_content', '')), metadata, float(point.score))
        top_score = max((float(p.score) for p in points), default=0.0)

    if bm25 is not None:
        for rank, (doc, _) in enumerate(bm25.search(query, candidate_k), start=1):
            chunk = bm25.chunks[doc]
            add(rank, chunk['id'], chunk['text'], dict(chunk['metadata']))

    base = {'query': query, 'carried': carried, 'top_score': top_score, 'warning': warning}

    # Không có đoạn nào đủ giống -> không để LLM đoán
    if min_score is not None and top_score is not None and top_score < min_score:
        return {**base, 'results': [],
                'reason': f'Độ tương đồng cao nhất {top_score:.2f} < ngưỡng {min_score}'}

    ranked = sorted(candidates.items(), key=lambda item: item[1]['rrf'], reverse=True)
    results = [
        {'id': chunk_id, 'text': entry['text'], 'metadata': entry['metadata'],
         'score': entry['dense'], 'rank_score': entry['rrf']}
        for chunk_id, entry in ranked[:k]
    ]
    return {**base, 'results': results, 'reason': None}


# ============================================================
# 3. CONTEXT FORMATTING - MỞ RỘNG & ĐỊNH DẠNG NGỮ CẢNH
# ============================================================

# Mục ngắn hơn ngưỡng này được đưa nguyên mục thay vì một mảnh
SECTION_EXPAND_CHARS = 2500
# Giới hạn tổng ngữ cảnh (~3.000-3.500 token tiếng Việt, vừa NUM_CTX 8192)
MAX_CONTEXT_CHARS = 9000


def _node_chunks(metadata, collection=None):
    """Tất cả chunk cùng mục (node), theo thứ tự trong tài liệu."""

    bm25 = _bm25(collection)
    node_id = metadata.get('node_id')
    if bm25 is None or node_id is None:
        return []
    return [bm25.chunks[d] for d in bm25.node_docs.get(node_id, [])]


def _strip_overlap(previous, current):
    """Bỏ phần lặp (overlap) ở đầu chunk sau so với cuối chunk trước."""

    for size in range(min(len(previous), len(current), 300), 20, -1):
        if previous.endswith(current[:size]):
            return current[size:]
    return current


def build_context_blocks(results, collection=None, max_chars=None):
    """Gom kết quả thành các khối ngữ cảnh, mở rộng thành cả mục khi mục ngắn."""

    blocks = []
    seen = set()
    used = 0

    for item in results:
        meta = item['metadata']
        node_id = meta.get('node_id')
        if node_id in seen:
            continue

        pieces = _node_chunks(meta, collection)
        full_length = sum(len(p['text']) for p in pieces)

        if pieces and full_length <= SECTION_EXPAND_CHARS:
            header, _, body = pieces[0]['text'].partition('\n') if meta.get('path') \
                else ('', '', pieces[0]['text'])
            for prev, piece in zip(pieces, pieces[1:]):
                rest = piece['text'].partition('\n')[2] if meta.get('path') else piece['text']
                body += '\n' + _strip_overlap(prev['text'], rest)
            text = f'{header}\n{body}' if header else body
            page_start = pieces[0]['metadata']['page_number']
            page_end = pieces[-1]['metadata'].get('page_end', page_start)
            seen.add(node_id)
        else:
            text = item['text']
            page_start = meta.get('page_number')
            page_end = meta.get('page_end', page_start)

        if used + len(text) > (max_chars or MAX_CONTEXT_CHARS) and blocks:
            break
        used += len(text)
        blocks.append({'text': text, 'metadata': meta, 'page_start': page_start,
                       'page_end': page_end, 'score': item.get('score')})

    return blocks


def _page_label(block):
    start, end = block['page_start'], block['page_end']
    return f'trang {start}' if not end or end == start else f'trang {start}-{end}'


def format_context(blocks):
    """Ghép các khối thành ngữ cảnh, mỗi khối có nhãn nguồn."""

    return '\n\n---\n\n'.join(
        f'[{block["metadata"].get("source_file")}, {_page_label(block)}]\n{block["text"]}'
        for block in blocks
    )


def build_sources(blocks):
    return [{
        'source_file': block['metadata'].get('source_file'),
        'page': block['page_start'],
        'page_end': block['page_end'],
        'title': ' › '.join(block['metadata'].get('path') or []),
        'score': block['score'],
        'excerpt': block['text'],
    } for block in blocks]


# ============================================================
# 4. QUESTION ANSWERING
# ============================================================

NO_DATA_ANSWER = ('Tài liệu hiện có chưa cung cấp đủ thông tin để trả lời câu hỏi này '
                  '(không tìm thấy đoạn tài liệu đủ liên quan).')


def prepare_answer(question, history=None):
    """
    Truy xuất + dựng ngữ cảnh, chưa gọi LLM.

    Returns:
        dict: context (str | None), sources, carried, top_score, reason, warning
    """

    retrieval = retrieve(question, history=history)
    blocks = build_context_blocks(retrieval['results'])

    return {
        **{key: retrieval[key] for key in ('carried', 'top_score', 'reason', 'warning')},
        'context': format_context(blocks) if blocks else None,
        'sources': build_sources(blocks),
    }


def answer_question(question, generation=None, history=None):
    """Hỏi đáp đầy đủ (không streaming)."""

    generation = generation or {}
    prepared = prepare_answer(question, history)

    if not prepared['context']:
        return {**prepared, 'answer': NO_DATA_ANSWER}

    answer = call_generation_api(question, prepared['context'],
                                 provider=generation.get('provider'),
                                 model=generation.get('model'))
    return {**prepared, 'answer': answer}


def stream_answer(prepared, question, generation=None):
    """Sinh câu trả lời dạng stream cho kết quả của prepare_answer()."""

    generation = generation or {}
    if not prepared['context']:
        yield NO_DATA_ANSWER
        return

    yield from stream_generation_api(question, prepared['context'],
                                     provider=generation.get('provider'),
                                     model=generation.get('model'))
