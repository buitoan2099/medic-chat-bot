"""
Sinh bộ câu hỏi đánh giá truy xuất từ chunks.jsonl (dùng cho mọi tài liệu).

Chạy (sau khi đã ingest hoặc ingest --dry-run):
    python -m evaluation.build_eval [--out evaluation/questions_new.jsonl]

Mỗi câu hỏi = (mục) + (chủ đề), đáp án là khoảng trang của chủ đề và tên mục.
Có biến thể gõ không dấu. Câu hỏi sinh theo mẫu nên dễ hơn câu hỏi thật;
dùng để SO SÁNH các phương án truy xuất, không phải đo chất lượng tuyệt đối.
Nên bổ sung câu hỏi viết tay vào natural_questions.jsonl.

Lưu ý: evaluation/questions.jsonl hiện có được tạo từ phiên bản trước cho
Dược thư 2018 và được giữ nguyên để so sánh các lần đo; mặc định script ghi
ra file khác để không ghi đè.
"""

import argparse
import json
import random
from pathlib import Path

from config import CHUNKS_FILE
from rag.pdf_parser import strip_accents

DEFAULT_OUT = Path(__file__).resolve().parent / 'questions_new.jsonl'
TEMPLATES = ['{section} của {topic}', '{topic}: {section}?', 'Cho biết {section} của {topic}']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--topics', type=int, default=50)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    topics = {}  # (file, topic) -> {pages, sections}
    for line in CHUNKS_FILE.open(encoding='utf-8'):
        meta = json.loads(line)['metadata']
        if not meta.get('topic'):
            continue
        entry = topics.setdefault((meta['source_file'], meta['topic']),
                                  {'pages': set(), 'sections': set()})
        entry['pages'].add(meta['page_number'])
        if meta.get('section'):
            entry['sections'].add(meta['section'])

    pool = [(key, v) for key, v in sorted(topics.items()) if v['sections'] and len(key[1]) <= 40]
    questions = []
    for i, ((source, topic), info) in enumerate(rng.sample(pool, min(args.topics, len(pool)))):
        for section in rng.sample(sorted(info['sections']), min(2, len(info['sections']))):
            question = rng.choice(TEMPLATES).format(section=section.lower(), topic=topic)
            variant = 'generic'
            if i % 2:
                question, variant = strip_accents(question), 'no_accent'
            questions.append({'question': question, 'type': variant, 'source_file': source,
                              'section': section, 'page_start': min(info['pages']),
                              'page_end': max(info['pages'])})

    with open(args.out, 'w', encoding='utf-8') as handle:
        for item in questions:
            handle.write(json.dumps(item, ensure_ascii=False) + '\n')
    print(f'Đã ghi {len(questions)} câu hỏi vào {args.out}')


if __name__ == '__main__':
    main()
