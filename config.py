import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

PDF_GLOB = os.getenv('PDF_GLOB', 'data/documents/duoc-thu-quoc-gia-viet-nam-2018.pdf')
QDRANT_DIR = BASE_DIR / os.getenv('QDRANT_DIR', 'qdrant_db')
COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'duoc_2018_v2')

# Dữ liệu phụ của từng collection: chunks (cho BM25), tiến độ ingest


def sidecar_paths(collection):
    """(thư mục, chunks.jsonl, ingest_state.json) của một collection."""

    folder = QDRANT_DIR / 'sidecar' / collection
    return folder, folder / 'chunks.jsonl', folder / 'ingest_state.json'


SIDECAR_DIR, CHUNKS_FILE, STATE_FILE = sidecar_paths(COLLECTION_NAME)

# Thư mục dữ liệu chạy của hệ thống chat (đặc tả 04) và địa chỉ backend cho UI
STORAGE_DIR = BASE_DIR / os.getenv('STORAGE_DIR', 'storage')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://127.0.0.1:8000').rstrip('/')
# Khoá cho API quản trị giai đoạn P1 (P2 thay bằng đăng nhập nhân sự)
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '').strip()
# Khoá ký token đăng nhập nhân sự (P2). Trống -> sinh tạm mỗi lần chạy (phải đăng nhập lại khi restart)
AUTH_SECRET = os.getenv('AUTH_SECRET', '').strip()
# Chế độ chạy thử: tạo sẵn tài khoản demo_* và cho đăng nhập một chạm (KHÔNG cần mật khẩu).
# Chỉ bật khi thử nghiệm; vận hành thật phải tắt.
DEMO_MODE = os.getenv('DEMO_MODE', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
# Mở trang Cấu hình model cho MỌI NGƯỜI (không cần nhập ADMIN_TOKEN): agent, prompt, cài đặt.
# Thao tác chỉ mục (dựng lại / huỷ / quay lại) vẫn phải nhập khoá. Vận hành thật nên tắt.
OPEN_MODEL_CONFIG = os.getenv('OPEN_MODEL_CONFIG', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

# ============================================================
# TRUY XUẤT (RETRIEVAL)
# ============================================================

# Số đoạn đưa vào ngữ cảnh cho LLM
TOP_K = int(os.getenv('TOP_K', '5'))
# Số ứng viên lấy từ mỗi nguồn (vector, BM25) trước khi gộp và xếp hạng lại
CANDIDATE_K = int(os.getenv('CANDIDATE_K', '30'))
# Ngưỡng cosine tối thiểu: thấp hơn -> trả lời "không tìm thấy" thay vì để LLM đoán.
MIN_SCORE = float(os.getenv('MIN_SCORE', '0.45'))

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').strip().rstrip('/')
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'bge-m3:latest')
GENERATION_MODEL = os.getenv('GENERATION_MODEL', 'qwen3:14b')


# ============================================================
# CHỌN MÔ HÌNH TRẢ LỜI - GENERATION PROVIDER
# ============================================================

# Provider mặc định cho phần sinh câu trả lời: ollama | gemini | openai
# Embedding vẫn luôn chạy qua Ollama để khớp với chỉ mục đã tạo.
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'ollama').strip().lower()

# Google Gemini (lấy key tại https://aistudio.google.com/apikey)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')

# OpenRouter (OpenAI-compatible, nhiều model; ":free" = miễn phí, có giới hạn lượt)
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '').strip()
OPENROUTER_BASE_URL = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1').strip().rstrip('/')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'nvidia/nemotron-3-ultra-550b-a55b:free').strip()

# OpenAI hoặc endpoint tương thích OpenAI (Groq, OpenRouter, DeepSeek...)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '').strip()
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').strip().rstrip('/')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')


def normalize_ollama_base_url(url=None):
    """Bỏ dấu / cuối và /v1 nếu người dùng đã khai báo kèm, tránh lặp /v1/v1."""
    base = (url or OLLAMA_BASE_URL).strip().rstrip('/')

    if base.endswith('/v1'):
        base = base[:-3]

    return base

GENERATION_TEMPERATURE = 0.1
GENERATION_MAX_TOKENS = 1024
# Cửa sổ ngữ cảnh cho qwen3. 3 chunk x 1400 ký tự + prompt cần nhiều hơn mức mặc định cũ (4096).
NUM_CTX = 8192

# ============================================================
# GIAO DIỆN & PROMPT (đổi theo tài liệu mà không cần sửa code)
# ============================================================

APP_TITLE = os.getenv('APP_TITLE', 'Tra cứu tài liệu')
APP_SUBTITLE = os.getenv('APP_SUBTITLE', 'Hỏi đáp dựa trên nội dung tài liệu PDF đã lập chỉ mục')
APP_NOTICE = os.getenv('APP_NOTICE', '')
# File chứa system prompt riêng (tuỳ chọn). Bỏ trống -> dùng prompt chung.
SYSTEM_PROMPT_FILE = os.getenv('SYSTEM_PROMPT_FILE', '').strip()
