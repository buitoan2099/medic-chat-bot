"""
Đo năng lực Ollama cho hệ thống chat 3 khung (P0, technical plan mục 5.2–5.3).

Chạy:
    python -m scripts.bench_ollama                     # mặc định: ctx 8k,16k · song song 1,2,4
    python -m scripts.bench_ollama --ctx 16384 --parallel 1,2 --runs 1

Đo:
1. Sinh văn bản (model GENERATION_MODEL): thời gian ra token đầu (TTFT), tổng thời
   gian, tốc độ sinh, khi chạy song song 1/2/4 yêu cầu, ở num_ctx 8k và 16k.
2. Ngữ cảnh có bị cắt im lặng không: prompt_eval_count so với số token dự kiến.
3. Hệ số ký tự/token tiếng Việt thực tế (để hiệu chỉnh ContextBuilder).
4. Embedding (EMBEDDING_MODEL): độ trễ 1 truy vấn và lô 16 đoạn, lúc rảnh và lúc
   đang có yêu cầu sinh văn bản.
5. Bộ nhớ: /api/ps sau khi chạy – hai model có cùng nằm trong bộ nhớ không.

Kết quả ghi ra docs/benchmarks/ollama-<ngày giờ>.md và .json.
Prompt lấy từ chunks.jsonl (nội dung tài liệu thật) để số token sát thực tế.
"""

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from config import (
    BASE_DIR,
    CHUNKS_FILE,
    EMBEDDING_MODEL,
    GENERATION_MODEL,
    normalize_ollama_base_url,
)

OUT_DIR = BASE_DIR / 'docs' / 'benchmarks'
# Ước lượng ban đầu, được hiệu chỉnh lại bằng prompt_eval_count đo được
CHARS_PER_TOKEN_GUESS = 2.5
# Tỉ lệ ngữ cảnh dùng cho prompt (phần còn lại dành cho đầu ra + biên)
PROMPT_FILL = 0.75


def load_corpus_text(limit_chars):
    if not CHUNKS_FILE.exists():
        raise SystemExit(f'Thiếu {CHUNKS_FILE}. Chạy: python -m rag.ingest --dry-run')
    parts, size = [], 0
    with CHUNKS_FILE.open(encoding='utf-8') as handle:
        for line in handle:
            text = json.loads(line)['text']
            parts.append(text)
            size += len(text) + 2
            if size >= limit_chars:
                break
    return '\n\n'.join(parts)[:limit_chars]


def build_prompt(corpus, num_ctx):
    chars = int(num_ctx * PROMPT_FILL * CHARS_PER_TOKEN_GUESS)
    context = corpus[:chars]
    question = 'Tóm tắt ngắn gọn các chống chỉ định được nhắc tới trong tài liệu trên.'
    return context, question, chars


def chat_once(base, model, num_ctx, context, question, num_predict):
    """Một yêu cầu /api/chat dạng stream. Trả về số đo."""

    started = time.perf_counter()
    first_token = None
    final = {}
    response = requests.post(
        f'{base}/api/chat',
        json={
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'Bạn là trợ lý tra cứu tài liệu. Trả lời bằng tiếng Việt.'},
                {'role': 'user', 'content': f'TÀI LIỆU:\n{context}\n\nCÂU HỎI: {question}'},
            ],
            'stream': True,
            'think': False,
            'keep_alive': '30m',
            'options': {'num_ctx': num_ctx, 'num_predict': num_predict, 'temperature': 0},
        },
        stream=True,
        timeout=(5, 900),
    )
    response.raise_for_status()
    for line in response.iter_lines():
        if not line:
            continue
        data = json.loads(line)
        if data.get('error'):
            raise RuntimeError(data['error'])
        if first_token is None and (data.get('message') or {}).get('content'):
            first_token = time.perf_counter() - started
        if data.get('done'):
            final = data
            break
    total = time.perf_counter() - started
    eval_s = final.get('eval_duration', 0) / 1e9
    prompt_s = final.get('prompt_eval_duration', 0) / 1e9
    return {
        'ttft_s': first_token,
        'total_s': total,
        'load_s': final.get('load_duration', 0) / 1e9,
        'prompt_tokens': final.get('prompt_eval_count'),
        'prompt_tok_per_s': (final.get('prompt_eval_count', 0) / prompt_s) if prompt_s else None,
        'output_tokens': final.get('eval_count'),
        'gen_tok_per_s': (final.get('eval_count', 0) / eval_s) if eval_s else None,
    }


def embed(base, model, texts):
    started = time.perf_counter()
    response = requests.post(f'{base}/api/embed', json={'model': model, 'input': texts,
                                                         'keep_alive': '30m'},
                             timeout=(5, 300))
    response.raise_for_status()
    return time.perf_counter() - started


def ps(base):
    try:
        data = requests.get(f'{base}/api/ps', timeout=10).json()
    except (requests.RequestException, ValueError):
        return []
    return [{'name': m.get('name'), 'size_gb': round(m.get('size', 0) / 1e9, 2),
             'vram_gb': round(m.get('size_vram', 0) / 1e9, 2),
             'context_length': m.get('context_length')} for m in data.get('models', [])]


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def fmt(value, digits=1):
    return '—' if value is None else f'{value:.{digits}f}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ctx', default='8192,16384')
    parser.add_argument('--parallel', default='1,2,4')
    parser.add_argument('--runs', type=int, default=2, help='Số lượt lặp mỗi cấu hình')
    parser.add_argument('--num-predict', type=int, default=300)
    parser.add_argument('--model', default=GENERATION_MODEL)
    parser.add_argument('--embed-model', default=EMBEDDING_MODEL)
    args = parser.parse_args()

    base = normalize_ollama_base_url()
    ctx_list = [int(x) for x in args.ctx.split(',')]
    par_list = [int(x) for x in args.parallel.split(',')]

    # 0. Kết nối và model
    try:
        version = requests.get(f'{base}/api/version', timeout=5).json().get('version')
        installed = [m['name'] for m in requests.get(f'{base}/api/tags', timeout=10).json()['models']]
    except requests.RequestException as error:
        raise SystemExit(f'Không kết nối được Ollama tại {base}: {error}\n'
                         'Kiểm tra Mac mini đã bật và Tailscale đang online.')
    for wanted in (args.model, args.embed_model):
        if not any(n == wanted or n.startswith(wanted + ':') for n in installed):
            raise SystemExit(f'Ollama thiếu model {wanted}. Chạy: ollama pull {wanted}')
    print(f'Ollama {version} tại {base} · model {args.model} · embedding {args.embed_model}')

    corpus = load_corpus_text(int(max(ctx_list) * CHARS_PER_TOKEN_GUESS))
    report = {'time': datetime.now().isoformat(timespec='seconds'), 'base_url': base,
              'ollama_version': version, 'model': args.model, 'embed_model': args.embed_model,
              'generation': [], 'embedding': {}, 'memory': {}}

    # 1–3. Sinh văn bản
    for num_ctx in ctx_list:
        context, question, chars = build_prompt(corpus, num_ctx)
        print(f'\n[ctx {num_ctx}] nạp model (lượt khởi động)...')
        warm = chat_once(base, args.model, num_ctx, context[:500], question, 5)
        for parallel in par_list:
            samples = []
            for run in range(args.runs):
                with ThreadPoolExecutor(parallel) as pool:
                    futures = [pool.submit(chat_once, base, args.model, num_ctx, context,
                                           question, args.num_predict) for _ in range(parallel)]
                    batch_started = time.perf_counter()
                    results = [f.result() for f in futures]
                    wall = time.perf_counter() - batch_started
                for r in results:
                    r['wall_s'] = wall
                samples.extend(results)
                print(f'  song song {parallel} · lượt {run + 1}: '
                      f'TTFT {fmt(median([r["ttft_s"] for r in results]))}s · '
                      f'tổng {fmt(wall)}s')
            prompt_tokens = median([s['prompt_tokens'] for s in samples])
            expected_tokens = chars / CHARS_PER_TOKEN_GUESS
            row = {
                'num_ctx': num_ctx, 'parallel': parallel, 'prompt_chars': chars,
                'prompt_tokens': prompt_tokens,
                'chars_per_token': (chars / prompt_tokens) if prompt_tokens else None,
                'truncated': bool(prompt_tokens and prompt_tokens >= num_ctx - 8),
                'ttft_s_median': median([s['ttft_s'] for s in samples]),
                'ttft_s_max': max((s['ttft_s'] or 0) for s in samples),
                'total_s_median': median([s['total_s'] for s in samples]),
                'gen_tok_per_s_median': median([s['gen_tok_per_s'] for s in samples]),
                'prompt_tok_per_s_median': median([s['prompt_tok_per_s'] for s in samples]),
                'expected_prompt_tokens': round(expected_tokens),
                'warmup_load_s': warm['load_s'],
            }
            report['generation'].append(row)

    # 4. Embedding: lúc rảnh và lúc đang sinh văn bản
    chunk_texts = corpus.split('\n\n')[:16]
    report['embedding']['idle_query_s'] = median([embed(base, args.embed_model, ['liều paracetamol'])
                                                  for _ in range(3)])
    report['embedding']['idle_batch16_s'] = embed(base, args.embed_model, chunk_texts)

    context, question, _ = build_prompt(corpus, ctx_list[-1])
    busy = []
    worker = threading.Thread(target=lambda: chat_once(base, args.model, ctx_list[-1], context,
                                                      question, args.num_predict))
    worker.start()
    time.sleep(1.0)
    for _ in range(3):
        busy.append(embed(base, args.embed_model, ['chống chỉ định ibuprofen']))
    worker.join()
    report['embedding']['busy_query_s'] = median(busy)

    # 5. Bộ nhớ
    loaded = ps(base)
    report['memory']['loaded_models'] = loaded
    names = [m['name'] for m in loaded]
    report['memory']['both_resident'] = (
        any(n.startswith(args.model.split(':')[0]) for n in names)
        and any(n.startswith(args.embed_model.split(':')[0]) for n in names))

    write_report(report)


def write_report(report):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M')
    (OUT_DIR / f'ollama-{stamp}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                  encoding='utf-8')
    lines = [
        f'# Đo năng lực Ollama – {report["time"]}', '',
        f'Ollama {report["ollama_version"]} · `{report["model"]}` · embedding `{report["embed_model"]}`', '',
        '## Sinh văn bản', '',
        '| num_ctx | Song song | Token prompt (dự kiến → thực) | Ký tự/token | Bị cắt? | TTFT trung vị / max (s) | Tổng trung vị (s) | Tốc độ sinh (tok/s) | Đọc prompt (tok/s) |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for r in report['generation']:
        lines.append(
            f'| {r["num_ctx"]} | {r["parallel"]} | {r["expected_prompt_tokens"]} → {fmt(r["prompt_tokens"], 0)} '
            f'| {fmt(r["chars_per_token"], 2)} | {"**CÓ**" if r["truncated"] else "không"} '
            f'| {fmt(r["ttft_s_median"])} / {fmt(r["ttft_s_max"])} | {fmt(r["total_s_median"])} '
            f'| {fmt(r["gen_tok_per_s_median"])} | {fmt(r["prompt_tok_per_s_median"], 0)} |')
    e = report['embedding']
    lines += ['', '## Embedding', '',
              f'- 1 truy vấn lúc rảnh: {fmt(e["idle_query_s"], 2)} s',
              f'- Lô 16 đoạn lúc rảnh: {fmt(e["idle_batch16_s"], 2)} s',
              f'- 1 truy vấn khi đang sinh văn bản: {fmt(e["busy_query_s"], 2)} s', '',
              '## Bộ nhớ (/api/ps)', '',
              f'- Hai model cùng nằm trong bộ nhớ: **{"có" if report["memory"]["both_resident"] else "KHÔNG"}**', '']
    for m in report['memory']['loaded_models']:
        lines.append(f'- `{m["name"]}`: {m["size_gb"]} GB (VRAM {m["vram_gb"]} GB), ctx {m["context_length"]}')
    lines += ['', '## Cách đọc', '',
              '- **Bị cắt = CÓ**: prompt chạm num_ctx, Ollama đã cắt ngữ cảnh im lặng → phải giảm ngân sách hoặc tăng num_ctx.',
              '- **Ký tự/token**: hệ số thực tế cho tiếng Việt; dùng thay 2,5 trong ContextBuilder.',
              '- So TTFT/tổng thời gian với NFR-1 (gợi ý ≤ 15 s) và NFR-2 (phân loại ≤ 3 s), technical plan mục 5.3.',
              '- Embedding khi đang sinh chậm hẳn → cần hàng đợi embedding riêng / ưu tiên.']
    path = OUT_DIR / f'ollama-{stamp}.md'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\nĐã ghi {path}')


if __name__ == '__main__':
    main()
