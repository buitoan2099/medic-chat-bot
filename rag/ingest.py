"""
Lập chỉ mục các tài liệu PDF vào Qdrant (dùng cho mọi loại tài liệu).

Chạy từ thư mục gốc:
    python -m rag.ingest --reset     # xoá collection và tạo lại
    python -m rag.ingest --resume    # tiếp tục lần chạy bị gián đoạn
    python -m rag.ingest --dry-run   # chỉ phân tích PDF, không embed

Quy trình:
- Đọc mọi PDF khớp PDF_GLOB; cấu trúc (header/footer, tiêu đề, mục, trang
  chỉ mục) được rag.pdf_parser tự suy ra, không cấu hình riêng cho tài liệu nào.
- Mỗi chunk là một phần nội dung nằm dưới một tiêu đề, mở đầu bằng đường dẫn
  tiêu đề (vd "Paracetamol › Chống chỉ định") để embedding biết ngữ cảnh.
- Ghi kèm chunks.jsonl cho tìm kiếm từ khoá (BM25).
"""

import argparse
import glob
from dataclasses import dataclass
import hashlib
import json
import os
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import (
    BASE_DIR,
    COLLECTION_NAME,
    PDF_GLOB,
    QDRANT_DIR,
    sidecar_paths,
)
from rag.embeddings import embed_texts
from rag.pdf_parser import extract_pages, page_at, parse_document


# ============================================================
# 1. CẤU HÌNH
# ============================================================

# Số chunk mỗi lần upsert (embed_texts tự chia nhỏ request bên trong)
BATCH = 32

# Kích thước phần nội dung của chunk (chưa tính dòng tiêu đề)
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

# Số tiêu đề tối đa ghi ở đầu chunk
PATH_DEPTH = 3

# Thư mục cache kết quả trích xuất PDF
CACHE_DIR = QDRANT_DIR / 'cache'


@dataclass(frozen=True)
class IngestTarget:
    """Collection đích và các file phụ đi kèm (chunks.jsonl, ingest_state.json)."""

    collection: str

    @property
    def chunks_file(self):
        return sidecar_paths(self.collection)[1]

    @property
    def state_file(self):
        return sidecar_paths(self.collection)[2]


DEFAULT_TARGET = IngestTarget(COLLECTION_NAME)


def write_ingest_state(target=DEFAULT_TARGET, **values):
    """Ghi tiến độ nguyên tử để có thể tiếp tục sau khi bị gián đoạn."""

    path = target.state_file
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def point_id(chunk_id, collection=COLLECTION_NAME):
    """Tạo UUID ổn định từ chunk_id, hợp lệ với Qdrant Local."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'{collection}/{chunk_id}'))


# ============================================================
# 2. TẠO CHUNKS
# ============================================================

def _splitter():
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=['\n', '. ', '; ', ', ', ' ', ''],
        add_start_index=True,
    )


def _display_path(node, topics):
    """
    Đường dẫn tiêu đề hiển thị ở đầu chunk: bắt đầu từ chủ đề (bỏ các tiêu đề
    bao ngoài như tên sách), tối đa PATH_DEPTH cấp.
    """

    path = list(node['path'])
    if node.get('topic_id') is not None:
        topic = topics[node['topic_id']]
        for i, heading in enumerate(path):
            if heading.replace('\n', ' ').lower().startswith(topic['name'][:12].lower()) \
                    or topic['name'].lower().startswith(heading[:12].lower()):
                path = [topic['name']] + path[i + 1:]
                break
    return [p.replace('\n', ' ') for p in path[-PATH_DEPTH:]]


def build_chunks(file_tag, source_file, document):
    """
    Returns:
        list[dict]: mỗi chunk gồm id, text (để embed), metadata.
    """

    splitter = _splitter()
    topics = document['topics']
    chunks = []

    for n_index, node in enumerate(document['nodes']):
        path = _display_path(node, topics)
        header = ' › '.join(path)
        node_id = f'{file_tag}-n{n_index:05d}'
        topic = topics[node['topic_id']]['name'] if node.get('topic_id') is not None else None

        for c_index, piece in enumerate(splitter.create_documents([node['text']]), start=1):
            start = max(piece.metadata.get('start_index', 0), 0)
            page = page_at(node['offsets'], start, node['page_start'])
            page_end = page_at(node['offsets'], start + len(piece.page_content),
                               node['page_start'])
            chunk_id = f'{node_id}-c{c_index:02d}'

            chunks.append({
                'id': chunk_id,
                'text': f'{header}\n{piece.page_content}' if header else piece.page_content,
                'metadata': {
                    'source_file': source_file,
                    'page_number': page,
                    'page_end': page_end,
                    'topic': topic,
                    'section': node.get('section'),
                    'path': path,
                    'node_id': node_id,
                    'chunk_id': chunk_id,
                },
            })

    return chunks


def load_documents(log=print):
    """Đọc mọi PDF theo PDF_GLOB, phân tích cấu trúc và tạo chunks."""

    files = sorted(glob.glob(str(BASE_DIR / PDF_GLOB)))
    if not files:
        raise FileNotFoundError(f'Không tìm thấy PDF theo PDF_GLOB: {PDF_GLOB}')

    chunks = []
    stats = {'pdf_files': len(files), 'pdf_pages': 0, 'topics': 0,
             'section_types': 0, 'index_pages': 0, 'files': []}

    for path in files:
        pdf = Path(path)
        log(f'Đang đọc PDF: {pdf.name}')
        pages = extract_pages(pdf, cache_dir=CACHE_DIR, log=log)
        document = parse_document(pages, log=log)

        # Tag ổn định theo tên file để chunk_id không trùng giữa các tài liệu
        file_tag = 'f' + hashlib.sha1(pdf.name.encode('utf-8')).hexdigest()[:8]
        file_chunks = build_chunks(file_tag, pdf.name, document)
        chunks.extend(file_chunks)

        doc_stats = document['stats']
        stats['pdf_pages'] += doc_stats['pages']
        stats['topics'] += doc_stats['topics']
        stats['section_types'] += doc_stats['section_types']
        stats['index_pages'] += doc_stats['index_pages']
        stats['files'].append({'file': pdf.name, 'chunks': len(file_chunks), **doc_stats})

    stats['pages'] = len({(c['metadata']['source_file'], c['metadata']['page_number'])
                          for c in chunks})
    return chunks, stats


def write_chunks_file(chunks, target=DEFAULT_TARGET):
    """Ghi chunks.jsonl (BM25 đọc file này, không cần Qdrant)."""

    path = target.chunks_file
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + '\n')
    os.replace(temporary, path)


# ============================================================
# 3. QDRANT
# ============================================================

class IngestCancelled(RuntimeError):
    pass


def create_collection(client, vector_size, target=DEFAULT_TARGET, reset=False, resume=False,
                      log=print):
    """Tạo collection. Đã tồn tại: resume -> dùng tiếp, reset -> xoá tạo lại."""

    name = target.collection
    if client.collection_exists(name):
        if resume:
            log(f'Tiếp tục collection hiện tại: {name}')
            return
        if not reset:
            raise SystemExit('Collection đã tồn tại. Chạy lại với: python -m rag.ingest --reset')
        log(f'Đang xóa Collection cũ: {name}')
        client.delete_collection(name)

    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    log(f'Đã tạo Collection: {name}')


def upsert_chunks(client, chunks, vector_size, stats, target=DEFAULT_TARGET, log=print,
                  should_cancel=None):
    """Embed theo batch và upsert; bỏ qua batch đã có (phục vụ --resume)."""

    total = len(chunks)
    name = target.collection

    for start in range(0, total, BATCH):
        if should_cancel and should_cancel():
            raise IngestCancelled('Đã huỷ lập chỉ mục')
        batch = chunks[start:start + BATCH]
        ids = [point_id(chunk['id'], name) for chunk in batch]

        existing = client.retrieve(collection_name=name, ids=ids,
                                   with_payload=False, with_vectors=False)
        existing_ids = {str(point.id) for point in existing}
        pending = [(pid, chunk) for pid, chunk in zip(ids, batch) if pid not in existing_ids]
        done = min(start + len(batch), total)

        if not pending:
            write_ingest_state(target, status='in_progress', completed_chunks=done,
                               total_chunks=total, vector_size=vector_size, **stats)
            log(f'Bỏ qua batch đã lập chỉ mục ({done}/{total})')
            continue

        vectors = embed_texts([chunk['text'] for _, chunk in pending])
        if len(vectors) != len(pending):
            raise ValueError(f'Số vector ({len(vectors)}) không khớp số chunk ({len(pending)})')

        points = []
        for (pid, chunk), vector in zip(pending, vectors):
            if len(vector) != vector_size:
                raise ValueError(f'Embedding dimension không hợp lệ: '
                                 f'{len(vector)}, mong đợi {vector_size}')
            points.append(PointStruct(
                id=pid,
                vector=vector,
                payload={'page_content': chunk['text'], 'metadata': chunk['metadata']},
            ))

        client.upsert(collection_name=name, points=points)
        write_ingest_state(target, status='in_progress', completed_chunks=done,
                           total_chunks=total, vector_size=vector_size, **stats)
        log(f'Đã lập chỉ mục {done}/{total} chunks')


def print_summary(client, chunks, target=DEFAULT_TARGET, log=print):
    lengths = [len(chunk['text']) for chunk in chunks]
    count = client.count(collection_name=target.collection, exact=True).count

    log('\n========== INGESTION SUMMARY ==========')
    log(f'Số chunk: {len(chunks)}')
    log(f'Độ dài chunk min/avg/max: {min(lengths)} {sum(lengths) // len(lengths)} {max(lengths)}')
    log(f'Số record trong Qdrant: {count}')
    log(f'Collection: {target.collection}')
    log(f'Index: {QDRANT_DIR}')
    log('=======================================\n')

    if count != len(chunks):
        raise RuntimeError(f'Số record trong Qdrant ({count}) không khớp số chunk ({len(chunks)})')


def run_ingest(client, target=DEFAULT_TARGET, reset=False, resume=False, dry_run=False,
               log=print, should_cancel=None):
    """
    Toàn bộ quy trình lập chỉ mục cho một collection, dùng chung cho CLI và backend
    (backend truyền client Qdrant dùng chung – technical plan R1).

    Returns:
        dict: thống kê.
    """

    log('\n[1/5] Đang đọc và phân tích PDF...')
    chunks, stats = load_documents(log=log)
    if not chunks:
        raise SystemExit('Không có chunk nào được tạo.')
    stats['chunks'] = len(chunks)
    log(f'Tổng số chunks: {len(chunks)}')
    write_chunks_file(chunks, target)
    log(f'Đã ghi {target.chunks_file.name} ({target.collection})')
    if dry_run:
        return stats

    log('\n[2/5] Đang xác định embedding dimension...')
    sample = embed_texts([chunks[0]['text']])
    if not sample or not sample[0]:
        raise RuntimeError('Không thể tạo embedding từ chunk đầu tiên.')
    vector_size = len(sample[0])
    log(f'Embedding dimension: {vector_size}')

    log('\n[3/5] Đang chuẩn bị collection...')
    create_collection(client, vector_size, target, reset=reset, resume=resume, log=log)
    write_ingest_state(target, status='in_progress', completed_chunks=0,
                       total_chunks=len(chunks), vector_size=vector_size, **stats)

    log('\n[4/5] Đang lập chỉ mục...')
    upsert_chunks(client, chunks, vector_size, stats, target, log=log, should_cancel=should_cancel)

    log('\n[5/5] Hoàn thành ingestion!')
    print_summary(client, chunks, target, log=log)
    write_ingest_state(target, status='complete', completed_chunks=len(chunks),
                       total_chunks=len(chunks), vector_size=vector_size, **stats)
    return stats


# ============================================================
# 4. MAIN (chế độ offline: chỉ chạy khi backend KHÔNG chạy)
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='PDF Ingestion to Qdrant')
    parser.add_argument('--reset', action='store_true', help='Xóa Collection cũ và tạo lại chỉ mục')
    parser.add_argument('--resume', action='store_true', help='Tiếp tục collection đang lập chỉ mục dở dang')
    parser.add_argument('--dry-run', action='store_true',
                        help='Chỉ phân tích PDF và ghi chunks.jsonl, không embed')
    parser.add_argument('--collection', default=COLLECTION_NAME, help='Collection đích')
    args = parser.parse_args()
    target = IngestTarget(args.collection)

    if args.dry_run:
        run_ingest(None, target, dry_run=True)
        return

    client = QdrantClient(path=str(QDRANT_DIR))
    try:
        run_ingest(client, target, reset=args.reset, resume=args.resume)
    finally:
        client.close()


if __name__ == '__main__':
    main()
