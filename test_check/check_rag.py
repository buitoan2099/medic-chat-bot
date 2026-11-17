"""Chạy: python -m test_check.check_rag "câu hỏi" (cần Ollama hoặc provider khác)."""

import sys

from rag.rag import answer_question

question = ' '.join(sys.argv[1:]) or 'Chống chỉ định của paracetamol là gì?'
result = answer_question(question)

if result.get('warning'):
    print('Cảnh báo:', result['warning'])
print('\nCâu trả lời:')
print(result['answer'])
print('\nTài liệu liên quan:')
for i, s in enumerate(result['sources'], start=1):
    score = f"{s['score']:.3f}" if s['score'] is not None else '—'
    print(f"{i}. {s['title']} | trang {s['page']} | điểm={score}")
