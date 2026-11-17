"""Sinh câu trả lời qua Ollama / Gemini / OpenAI-compatible (thường và streaming)."""

import json
from functools import lru_cache

import requests
from openai import OpenAI

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GENERATION_MAX_TOKENS,
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
    LLM_PROVIDER,
    NUM_CTX,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    normalize_ollama_base_url,
)
from provider.http import LOCAL, REMOTE, error_message, post
from provider.prompts import SYSTEM_PROMPT, ThinkFilter, build_user_prompt, clean_response

# ============================================================
# 2. GENERATION - SINH CÂU TRẢ LỜI
# ============================================================

GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/models'

# ------------------------------------------------------------
# Ollama
# ------------------------------------------------------------

def _ollama_payload(question, context, model, stream):
    return {
        'model': model or GENERATION_MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': build_user_prompt(question, context)},
        ],
        'stream': stream,
        'think': False,
        'keep_alive': '30m',
        'options': {
            'temperature': GENERATION_TEMPERATURE,
            'num_predict': GENERATION_MAX_TOKENS,
            'num_ctx': NUM_CTX,
        },
    }


def _ollama_post(question, context, model, stream):
    base_url = normalize_ollama_base_url()
    return post(
        LOCAL,
        f'{base_url}/api/chat',
        label='Ollama',
        hint=f'({base_url}) Kiểm tra Mac mini đã bật và Tailscale đang online.',
        timeout=(10, 600),  # (kết nối, đọc)
        json=_ollama_payload(question, context, model, stream),
        stream=stream,
    )


def call_ollama_api(question, context, model=None):
    """
    Gửi câu hỏi và ngữ cảnh đến Ollama để tạo câu trả lời.

    Raises:
        RuntimeError: Nếu không kết nối được Ollama hoặc Ollama trả lỗi.
    """

    response = _ollama_post(question, context, model, stream=False)
    return clean_response(response.json()['message']['content'])


def stream_ollama_api(question, context, model=None):
    """Như call_ollama_api nhưng trả về từng đoạn chữ (NDJSON stream)."""

    response = _ollama_post(question, context, model, stream=True)
    with response:
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get('error'):
                raise RuntimeError(f'Ollama lỗi: {data["error"]}')
            piece = (data.get('message') or {}).get('content')
            if piece:
                yield piece
            if data.get('done'):
                break

# ------------------------------------------------------------
# Gemini
# ------------------------------------------------------------

def _gemini_request(question, context, model, api_key):
    key = (api_key or GEMINI_API_KEY).strip()
    model_name = model or GEMINI_MODEL

    if not key:
        raise RuntimeError(
            'Chưa cấu hình GEMINI_API_KEY trong .env. '
            'Lấy key tại https://aistudio.google.com/apikey'
        )

    generation_config = {
        'temperature': GENERATION_TEMPERATURE,
        'maxOutputTokens': GENERATION_MAX_TOKENS,
    }

    # Các model Gemini 2.5 Flash bật "thinking" mặc định, làm chậm phản hồi.
    # Tắt suy nghĩ ngầm cho phần tra cứu văn bản.
    if 'gemini-2.5-flash' in model_name:
        generation_config['thinkingConfig'] = {'thinkingBudget': 0}

    payload = {
        'system_instruction': {'parts': [{'text': SYSTEM_PROMPT}]},
        'contents': [
            {'role': 'user', 'parts': [{'text': build_user_prompt(question, context)}]},
        ],
        'generationConfig': generation_config,
    }
    headers = {'x-goog-api-key': key, 'Content-Type': 'application/json'}
    return model_name, headers, payload


def _gemini_text(data):
    candidates = data.get('candidates') or []
    if not candidates:
        block_reason = (data.get('promptFeedback') or {}).get('blockReason')
        if block_reason:
            raise RuntimeError(f'Gemini không trả về nội dung (blockReason={block_reason})')
        return '', None
    parts = (candidates[0].get('content') or {}).get('parts') or []
    return ''.join(part.get('text', '') for part in parts), candidates[0].get('finishReason')


def call_gemini_api(question, context, model=None, api_key=None):
    """
    Sinh câu trả lời bằng Google Gemini qua REST API.

    Raises:
        RuntimeError: Nếu thiếu API key hoặc Gemini trả lỗi.
    """

    model_name, headers, payload = _gemini_request(question, context, model, api_key)
    response = post(REMOTE, f'{GEMINI_BASE_URL}/{model_name}:generateContent',
                    label='Gemini', timeout=(10, 300), headers=headers, json=payload)

    content, finish_reason = _gemini_text(response.json())
    if not content.strip():
        raise RuntimeError(
            'Gemini trả về nội dung rỗng'
            + (f' (finishReason={finish_reason})' if finish_reason else '')
        )

    return clean_response(content)


def stream_gemini_api(question, context, model=None, api_key=None):
    """Streaming qua streamGenerateContent (Server-Sent Events)."""

    model_name, headers, payload = _gemini_request(question, context, model, api_key)
    response = post(REMOTE, f'{GEMINI_BASE_URL}/{model_name}:streamGenerateContent?alt=sse',
                    label='Gemini', timeout=(10, 300), headers=headers, json=payload,
                    stream=True)
    with response:
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith('data:'):
                continue
            text, _ = _gemini_text(json.loads(line[5:].strip()))
            if text:
                yield text

# ------------------------------------------------------------
# OpenAI
# ------------------------------------------------------------

@lru_cache(maxsize=8)
def _openai_client(api_key, base_url):
    """Tái sử dụng client (và connection pool bên trong) giữa các lần gọi."""
 
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=300,
        max_retries=3,  # SDK tự retry 429/5xx với backoff
    )

def call_openai_api(question, context, model=None, api_key=None, base_url=None):
    """
    Sinh câu trả lời bằng OpenAI hoặc endpoint tương thích OpenAI.
    """

    key = (api_key or OPENAI_API_KEY).strip()

    if not key:
        raise RuntimeError(
            'Chưa cấu hình OPENAI_API_KEY trong .env.'
        )

    model_name = model or OPENAI_MODEL
    client = _openai_client(key, (base_url or OPENAI_BASE_URL).rstrip('/'))

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': build_user_prompt(question, context),
                },
            ],
            temperature=GENERATION_TEMPERATURE,
            max_tokens=GENERATION_MAX_TOKENS,
        )
    except Exception as error:
        raise RuntimeError(
            f'Lỗi gọi OpenAI ({model_name}): {error}'
        ) from error

    return clean_response(response.choices[0].message.content)


def stream_openai_api(question, context, model=None, api_key=None, base_url=None):
    """Streaming qua OpenAI SDK (stream=True)."""

    key = (api_key or OPENAI_API_KEY).strip()
    if not key:
        raise RuntimeError('Chưa cấu hình OPENAI_API_KEY trong .env.')

    model_name = model or OPENAI_MODEL
    client = _openai_client(key, (base_url or OPENAI_BASE_URL).rstrip('/'))

    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': build_user_prompt(question, context)},
            ],
            temperature=GENERATION_TEMPERATURE,
            max_tokens=GENERATION_MAX_TOKENS,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as error:
        raise RuntimeError(f'Lỗi gọi OpenAI ({model_name}): {error}') from error

# ------------------------------------------------------------
# Điều phối theo provider
# ------------------------------------------------------------

_GENERATORS = {
    'ollama': call_ollama_api,
    'gemini': call_gemini_api,
    'openai': call_openai_api,
}
 
_STREAMERS = {
    'ollama': stream_ollama_api,
    'gemini': stream_gemini_api,
    'openai': stream_openai_api,
}

PROVIDER_NAMES = tuple(_GENERATORS)

def _normalize_provider(provider):
    return (provider or LLM_PROVIDER).strip().lower()

def call_generation_api(question, context, provider=None, model=None):
    """
    Điều phối việc sinh câu trả lời theo provider được chọn.
 
    Args:
        question (str): Câu hỏi của người dùng.
        context (str): Ngữ cảnh truy xuất từ Qdrant.
        provider (str | None): ollama | gemini | openai.
        model (str | None): Tên model tương ứng provider.
 
    Returns:
        str: Câu trả lời của mô hình.
 
    Raises:
        ValueError: Provider không hỗ trợ.
        RuntimeError: Lỗi kết nối/API, hoặc mô hình trả về nội dung rỗng.
    """
 
    selected = _normalize_provider(provider)
    generate = _GENERATORS.get(selected)
 
    if generate is None:
        raise ValueError(
            f'Provider không hỗ trợ: {selected}. '
            f'Chọn một trong: {", ".join(PROVIDER_NAMES)}'
        )
 
    answer = generate(question, context, model=model)
 
    if not answer:
        raise RuntimeError(f'{selected} trả về câu trả lời rỗng.')
 
    return answer

def stream_generation_api(question, context, provider=None, model=None):
    """
    Như call_generation_api nhưng trả về generator các đoạn chữ, đã lọc khối
    <think>...</think>. Dùng với st.write_stream().
    """

    selected = _normalize_provider(provider)
    stream = _STREAMERS.get(selected)

    if stream is None:
        raise ValueError(
            f'Provider không hỗ trợ: {selected}. '
            f'Chọn một trong: {", ".join(PROVIDER_NAMES)}'
        )

    think = ThinkFilter()
    produced = False

    for piece in stream(question, context, model=model):
        text = think.feed(piece)
        if text:
            produced = True
            yield text

    tail = think.flush()
    if tail:
        produced = True
        yield tail

    if not produced:
        raise RuntimeError(f'{selected} trả về câu trả lời rỗng.')

# ------------------------------------------------------------
# Kiểm tra kết nối (không sinh văn bản)
# ------------------------------------------------------------

def _check_ollama(model):
    base_url = normalize_ollama_base_url()
    response = LOCAL.get(f'{base_url}/api/tags', timeout=10)
 
    if response.status_code != 200:
        return False, f'Ollama trả về HTTP {response.status_code} tại {base_url}'
 
    installed = [
        item.get('name', '') for item in response.json().get('models', [])
    ]
    wanted = model or GENERATION_MODEL
 
    if not any(
        name == wanted or name.startswith(wanted + ':') for name in installed
    ):
        return False, (
            f'Kết nối Ollama OK nhưng thiếu model "{wanted}". '
            f'Chạy: ollama pull {wanted}'
        )
 
    return True, f'Ollama OK · {base_url} · model {wanted}'
 
 
def _check_gemini(model):
    if not GEMINI_API_KEY:
        return False, 'Thiếu GEMINI_API_KEY trong .env'
 
    model_name = model or GEMINI_MODEL
    response = REMOTE.get(
        f'{GEMINI_BASE_URL}/{model_name}',
        headers={'x-goog-api-key': GEMINI_API_KEY},
        timeout=15,
    )
 
    if response.status_code == 200:
        return True, f'Gemini OK · model {model_name}'
 
    return False, (
        f'Gemini lỗi HTTP {response.status_code}: {error_message(response)}'
    )
 
 
def _check_openai(model):
    if not OPENAI_API_KEY:
        return False, 'Thiếu OPENAI_API_KEY trong .env'
 
    base_url = OPENAI_BASE_URL.rstrip('/')
    response = REMOTE.get(
        f'{base_url}/models',
        headers={'Authorization': f'Bearer {OPENAI_API_KEY}'},
        timeout=15,
    )
 
    if response.status_code == 200:
        return True, f'OpenAI-compatible OK · {base_url}'
 
    return False, f'Lỗi HTTP {response.status_code}: {error_message(response)}'
 
 
_CHECKERS = {
    'ollama': _check_ollama,
    'gemini': _check_gemini,
    'openai': _check_openai,
}
 
 
def check_generation_connection(provider=None, model=None):
    """
    Kiểm tra nhanh kết nối/khóa API của provider mà không sinh văn bản.
 
    Returns:
        tuple[bool, str]: (thành công, thông điệp hiển thị cho người dùng).
    """
 
    selected = _normalize_provider(provider)
    check = _CHECKERS.get(selected)
 
    if check is None:
        return False, f'Provider không hỗ trợ: {selected}'
 
    try:
        return check(model)
    except requests.exceptions.RequestException as error:
        return False, f'Không kết nối được: {error}'
 