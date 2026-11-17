"""
Đánh giá truy xuất trên evaluation/questions.jsonl.

Chạy (tắt app Streamlit trước vì Qdrant local chỉ cho 1 process):
    python -m evaluation.run_eval                 # mọi phương án
    python -m evaluation.run_eval --methods bm25  # không cần Ollama

Phương án:
    baseline  Collection cũ (BASELINE_COLLECTION), chỉ tìm vector, như app cũ
    dense     Collection mới, chỉ tìm vector
    bm25      Collection mới, chỉ tìm từ khoá
    hybrid    Collection mới, quy trình đầy đủ của rag.retrieve()

Chỉ số (trên top 10 kết quả):
    page@k     có kết quả thuộc khoảng trang của chủ đề đúng
               (so sánh được giữa collection cũ và mới)
    section@k  kết quả thuộc trang đúng VÀ đúng mục
               Collection cũ không có metadata mục nên dò tên mục trong văn bản.
    MRR        nghịch đảo hạng của kết quả page-đúng đầu tiên
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

from config import COLLECTION_NAME
from rag.embeddings import embed_query
from rag.lexical import get_index
from rag.pdf_parser import fold
from rag.rag import open_vector_store, retrieve

QUESTIONS_FILE = Path(__file__).resolve().parent / 'questions.jsonl'
# Câu hỏi viết tay theo kiểu người dùng thật (không dùng để tinh chỉnh tham số)
NATURAL_FILE = Path(__file__).resolve().parent / 'natural_questions.jsonl'
RESULTS_FILE = Path(__file__).resolve().parent / 'results.json'
BASELINE_COLLECTION = os.getenv('BASELINE_COLLECTION', 'duoc_2018_pdf')
DEPTH = 10


def _section_in_text(section, text):
    """Dò tên mục trong văn bản (cho collection cũ). 'Chỉ định' ≠ 'Chống chỉ định'."""

    name = section.split(' (')[0]
    pattern = re.escape(name)
    if name == 'Chỉ định':
        pattern = r'(?<!Chống )(?<!chống )Chỉ định'
    return re.search(pattern, text) is not None


def _section_key(name):
    """'Tác dụng không mong muốn (ADR)' ~ 'Tác dụng không mong muốn'."""

    return fold(re.sub(r'\([^)]*\)', '', name or ''))


def judge(item, results):
    """Trả về danh sách (page_ok, section_ok) cho từng kết quả."""

    wanted = {_section_key(s) for s in item['sections']}
    verdicts = []
    for result in results:
        meta = result['metadata']
        page = meta.get('page_number')
        page_ok = page is not None and item['page_start'] <= page <= item['page_end']

        if item['type'] == 'chapter':
            section_ok = page_ok
        elif 'node_id' in meta:  # collection mới: có metadata mục
            section_ok = page_ok and _section_key(meta.get('section')) in wanted
        else:                    # collection cũ: dò tên mục trong văn bản
            section_ok = page_ok and any(_section_in_text(s, result['text'])
                                         for s in item['sections'])
        verdicts.append((page_ok, section_ok))
    return verdicts


def method_baseline(client):
    def run(question):
        points = client.query_points(collection_name=BASELINE_COLLECTION,
                                     query=embed_query(question), limit=DEPTH,
                                     with_payload=True).points
        return [{'text': str((p.payload or {}).get('page_content', '')),
                 'metadata': dict((p.payload or {}).get('metadata', {}))} for p in points]
    return run


def method_dense(client):
    def run(question):
        points = client.query_points(collection_name=COLLECTION_NAME,
                                     query=embed_query(question), limit=DEPTH,
                                     with_payload=True).points
        return [{'text': str((p.payload or {}).get('page_content', '')),
                 'metadata': dict((p.payload or {}).get('metadata', {}))} for p in points]
    return run


def method_bm25(client):
    index = get_index()

    def run(question):
        return [{'text': index.chunks[i]['text'], 'metadata': index.chunks[i]['metadata']}
                for i, _ in index.search(question, DEPTH)]
    return run


def method_hybrid(client):
    def run(question):
        return retrieve(question, k=DEPTH, client=client)['results']
    return run


METHODS = {'baseline': method_baseline, 'dense': method_dense,
           'bm25': method_bm25, 'hybrid': method_hybrid}


def summarize(rows):
    n = len(rows)
    if not n:
        return {}

    def hit(key, k):
        return sum(any(v[key] for v in row[:k]) for row in rows) / n

    mrr = 0.0
    for row in rows:
        for rank, verdict in enumerate(row, start=1):
            if verdict[0]:
                mrr += 1 / rank
                break

    return {
        'n': n,
        'page@1': hit(0, 1), 'page@3': hit(0, 3), 'page@5': hit(0, 5),
        'section@1': hit(1, 1), 'section@3': hit(1, 3), 'section@5': hit(1, 5),
        'mrr': mrr / n,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--methods', default='baseline,dense,bm25,hybrid')
    args = parser.parse_args()

    questions = []
    for path in (QUESTIONS_FILE, NATURAL_FILE):
        if path.exists():
            questions += [json.loads(line) for line in path.open(encoding='utf-8')]
    for item in questions:
        # Chuẩn hoá: cho phép nhiều mục đều được tính là đúng
        item.setdefault('sections', [item.get('section')])
    methods = [m.strip() for m in args.methods.split(',') if m.strip()]
    needs_qdrant = any(m != 'bm25' for m in methods)
    client = open_vector_store() if needs_qdrant else None

    report = {}
    try:
        if client is not None and 'baseline' in methods \
                and not client.collection_exists(BASELINE_COLLECTION):
            print(f'Bỏ qua baseline: không có collection {BASELINE_COLLECTION}')
            methods.remove('baseline')

        for name in methods:
            run = METHODS[name](client)
            rows_by_type = {}
            started = time.perf_counter()
            for item in questions:
                verdicts = judge(item, run(item['question']))
                rows_by_type.setdefault(item['type'], []).append(verdicts)
                rows_by_type.setdefault('ALL', []).append(verdicts)
            elapsed = time.perf_counter() - started
            report[name] = {t: summarize(rows) for t, rows in rows_by_type.items()}
            report[name]['ALL']['seconds_per_query'] = elapsed / len(questions)
            print(f'{name}: xong {len(questions)} câu trong {elapsed:.1f}s')
    finally:
        if client is not None:
            client.close()

    RESULTS_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    cols = ['page@1', 'page@3', 'page@5', 'section@1', 'section@5', 'mrr']
    for group in ['ALL', 'generic', 'no_accent', 'brand', 'chapter', 'natural']:
        print(f'\n== {group} ==')
        print(f'{"method":<10}' + ''.join(f'{c:>11}' for c in cols))
        for name, groups in report.items():
            stats = groups.get(group)
            if stats:
                print(f'{name:<10}' + ''.join(f'{stats[c]:>11.3f}' for c in cols))
    print(f'\nĐã lưu {RESULTS_FILE}')


if __name__ == '__main__':
    main()
