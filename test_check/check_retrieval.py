"""Chạy: python -m test_check.check_retrieval "câu hỏi" [--no-dense]"""

import sys

from rag.rag import retrieve

args = [a for a in sys.argv[1:] if a != '--no-dense']
question = ' '.join(args) or 'Liều dùng amoxicilin cho trẻ em'
result = retrieve(question, use_dense='--no-dense' not in sys.argv)

print('Truy vấn:', result['query'], '| top cosine:', result['top_score'])
if result.get('warning'):
    print('Cảnh báo:', result['warning'])
for rank, item in enumerate(result['results'], start=1):
    meta = item['metadata']
    text = item['text'].replace('\n', ' ')[:160]
    print(rank, f"{item['rank_score']:.4f}", ' › '.join(meta.get('path') or []),
          'trang', meta.get('page_number'), '|', text + '...')
