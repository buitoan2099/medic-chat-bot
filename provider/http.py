"""Hạ tầng HTTP dùng chung cho các provider: session, retry, xử lý lỗi."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def make_session(retries):
    """
    Tạo Session có connection pooling và retry.

    - Thử lại khi lỗi kết nối hoặc HTTP 429/5xx, chờ tăng dần (1s, 2s, 4s...)
      và tôn trọng header Retry-After.
    - KHÔNG thử lại khi đã gửi xong mà chờ phản hồi quá lâu (read=0), vì mỗi
      lần chờ có thể kéo dài hàng phút.
    - raise_on_status=False: hết lượt thử vẫn trả response cuối để code bên
      dưới đọc được thông điệp lỗi.
    """

    retry = Retry(
        total=retries,
        connect=retries,
        read=0,
        status=retries,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({'GET', 'POST'}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    return session


REMOTE = make_session(retries=3)  # Gemini / OpenAI-compatible
LOCAL = make_session(retries=1)   # Ollama (mạng nội bộ/Tailscale)


def error_message(response):
    """Lấy thông điệp lỗi dễ đọc từ phản hồi của bất kỳ provider nào."""

    try:
        data = response.json()
    except ValueError:
        return response.text[:300]

    error = data.get('error') if isinstance(data, dict) else None

    if isinstance(error, dict):
        return error.get('message') or str(error)[:300]

    return str(error or data)[:300]


def post(session, url, *, label, timeout, hint='', **kwargs):
    """POST + gom xử lý lỗi kết nối và HTTP khác 200 vào một chỗ."""

    try:
        response = session.post(url, timeout=timeout, **kwargs)
    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            f'Không kết nối được {label}: {error}. {hint}'.strip()
        ) from error

    if response.status_code != 200:
        raise RuntimeError(
            f'{label} lỗi HTTP {response.status_code}: '
            f'{error_message(response)}'
        )

    return response