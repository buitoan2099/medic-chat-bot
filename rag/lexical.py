"""
Tìm kiếm từ khoá BM25 trên chunks.jsonl (bổ trợ cho tìm kiếm vector).

Vector embedding mạnh về ngữ nghĩa nhưng yếu với tên riêng, mã số, con số
gần giống nhau. BM25 khớp chính xác từ nên bù
được điểm yếu này. Văn bản được bỏ dấu + thêm bigram để khớp cụm từ.
"""

import json
import math
import threading

import numpy as np

from config import CHUNKS_FILE
from rag.pdf_parser import fold


K1 = 1.2
B = 0.75


def tokenize(text):
    """Từ không dấu + cặp từ liền kề (bigram)."""

    words = fold(text).split()
    return words + [f'{a}_{b}' for a, b in zip(words, words[1:])]


class BM25Index:

    def __init__(self, chunks):
        self.chunks = chunks
        self.by_id = {chunk['id']: i for i, chunk in enumerate(chunks)}
        n = len(chunks)

        postings = {}
        lengths = np.zeros(n, dtype=np.float32)

        for doc, chunk in enumerate(chunks):
            tokens = tokenize(chunk['text'])
            lengths[doc] = len(tokens)
            counts = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            for token, tf in counts.items():
                postings.setdefault(token, []).append((doc, tf))

        avg = float(lengths.mean()) if n else 1.0
        self.norm = K1 * (1 - B + B * lengths / avg)
        self.postings = {}
        self.idf = {}

        for token, items in postings.items():
            docs = np.fromiter((d for d, _ in items), dtype=np.int32, count=len(items))
            tfs = np.fromiter((t for _, t in items), dtype=np.float32, count=len(items))
            self.postings[token] = (docs, tfs)
            df = len(items)
            self.idf[token] = math.log(1 + (n - df + 0.5) / (df + 0.5))

        # Các chunk của cùng một mục (node), theo thứ tự — dùng để mở rộng ngữ cảnh
        self.node_docs = {}
        for doc, chunk in enumerate(chunks):
            node_id = chunk['metadata'].get('node_id')
            if node_id is not None:
                self.node_docs.setdefault(node_id, []).append(doc)

    def scores(self, query):
        result = np.zeros(len(self.chunks), dtype=np.float32)
        for token in set(tokenize(query)):
            if token not in self.postings:
                continue
            docs, tfs = self.postings[token]
            result[docs] += self.idf[token] * tfs * (K1 + 1) / (tfs + self.norm[docs])
        return result

    def search(self, query, k=30):
        """
        Returns:
            list[tuple[int, float]]: (chỉ số chunk, điểm BM25), giảm dần.
        """

        scores = self.scores(query)
        k = min(k, len(scores))
        if k == 0:
            return []
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]


_lock = threading.Lock()
_cache = {}  # đường dẫn chunks.jsonl -> (mtime, BM25Index)


def get_index(chunks_file=None):
    """
    Chỉ mục BM25 cho một chunks.jsonl (mặc định: collection trong .env), dựng lại
    khi file thay đổi. Trả về None nếu chưa có file.
    """

    path = chunks_file or CHUNKS_FILE
    if not path.exists():
        return None

    key = path.stat().st_mtime
    with _lock:
        cached = _cache.get(str(path))
        if cached is None or cached[0] != key:
            with path.open(encoding='utf-8') as handle:
                chunks = [json.loads(line) for line in handle]
            _cache[str(path)] = (key, BM25Index(chunks))
        return _cache[str(path)][1]
