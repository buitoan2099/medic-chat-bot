import httpx

# Thư viện NumPy: dùng để chuyển đổi và tính toán trên vector embedding.
import numpy as np

# OpenAI SDK: dùng để gửi request đến API tương thích với OpenAI.
# Ở đây, ta sử dụng SDK để giao tiếp với Ollama thông qua OpenAI-compatible API.
from openai import APIConnectionError, APITimeoutError, OpenAI

# Import tên model embedding và địa chỉ Ollama từ file config.py.
from config import EMBEDDING_MODEL, OLLAMA_BASE_URL, normalize_ollama_base_url


# Biến lưu client đã khởi tạo.
# Ban đầu là None, nghĩa là client chưa được tạo.
# Sau lần đầu sử dụng, client sẽ được tái sử dụng cho các request tiếp theo.
_client = None


def _get_client():
    """
    Lấy OpenAI client dùng để giao tiếp với Ollama.

    Nếu client chưa tồn tại thì khởi tạo mới.
    Nếu đã tồn tại thì sử dụng lại để tránh khởi tạo nhiều lần.
    """
    # Cho phép hàm thay đổi biến _client được khai báo ở phạm vi toàn cục.
    global _client

    # Chỉ khởi tạo client trong lần gọi đầu tiên.
    if _client is None:
        # Chuẩn hóa base URL: bỏ dấu / ở cuối và bỏ /v1 nếu người dùng
        # đã lỡ khai báo kèm trong OLLAMA_BASE_URL, tránh bị lặp thành /v1/v1.
        base_url = normalize_ollama_base_url()

        _client = OpenAI(
            # Ollama hỗ trợ OpenAI-compatible API tại endpoint /v1.
            # Ví dụ: http://localhost:11434/v1
            base_url=base_url + '/v1',

            # API key giả lập để khởi tạo OpenAI SDK khi dùng Ollama cục bộ.
            # Giá trị này không phải API key OpenAI thật.
            api_key='ollama',

            # Kết nối tối đa 5 giây: Mac mini/Tailscale tắt thì báo lỗi nhanh
            # (để app chuyển sang tìm theo từ khoá) thay vì treo nhiều phút.
            timeout=httpx.Timeout(300.0, connect=5.0),
            max_retries=1,
        )

    # Trả về client đã khởi tạo để thực hiện các request.
    return _client


def _normalize(vector):
    """
    Chuẩn hóa vector embedding về độ dài 1 (L2 normalization).

    Ví dụ:
        Vector đầu vào: [3, 4]
        Độ dài vector: 5
        Vector đầu ra: [0.6, 0.8]

    Nếu vector có độ dài bằng 0 thì giữ nguyên vector.
    """
    # Chuyển vector thành mảng NumPy với kiểu số thực float32.
    # float32 thường phù hợp để lưu trữ và xử lý embedding.
    arr = np.asarray(vector, dtype=np.float32)

    # Tính độ dài L2 của vector.
    norm = np.linalg.norm(arr)

    # Nếu độ dài lớn hơn 0 thì chia từng phần tử cho độ dài.
    # Nếu độ dài bằng 0 thì giữ nguyên vector.
    # .tolist() chuyển mảng NumPy trở lại thành Python list.
    return (arr / norm if norm > 0 else arr).tolist()


def embed_texts(texts, batch_size=16):
    """
    Tạo embedding cho danh sách văn bản bằng model Ollama.

    Args:
        texts: Danh sách văn bản cần chuyển thành vector.
        batch_size: Số văn bản gửi trong mỗi request, mặc định là 16.

    Returns:
        Danh sách vector embedding đã được chuẩn hóa.

    Ví dụ:
        texts = ["Nội dung A", "Nội dung B"]

        Kết quả:
        [
            [0.12, 0.34, ...],  # Vector của nội dung A
            [0.56, 0.78, ...]   # Vector của nội dung B
        ]
    """
    # Danh sách chứa toàn bộ vector embedding sau khi xử lý.
    vectors = []

    # Chia danh sách văn bản thành nhiều batch.
    # Ví dụ 35 văn bản, batch_size=16:
    # Batch 1: 16 văn bản
    # Batch 2: 16 văn bản
    # Batch 3: 3 văn bản
    for start in range(0, len(texts), batch_size):

        # Lấy các văn bản thuộc batch hiện tại.
        batch = texts[start:start + batch_size]

        # Gửi request tạo embedding đến Ollama thông qua OpenAI SDK.
        # model: model embedding được khai báo trong config.py.
        # input: danh sách văn bản cần tạo embedding.
        try:
            resp = _get_client().embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
            )
        except (APIConnectionError, APITimeoutError) as error:
            raise RuntimeError(
                'Không kết nối được Ollama để tạo embedding tại '
                f'{OLLAMA_BASE_URL}. Kiểm tra Mac mini đã bật và '
                'Tailscale đang online.'
            ) from error

        # Lấy vector embedding của từng văn bản trong kết quả trả về.
        # Chuẩn hóa từng vector trước khi thêm vào danh sách kết quả.
        vectors.extend(
            _normalize(d.embedding)
            for d in resp.data
        )

    # Trả về danh sách vector theo thứ tự các văn bản đầu vào.
    return vectors


def embed_query(text):
    """
    Tạo embedding cho một câu truy vấn duy nhất.

    Hàm này sử dụng lại embed_texts() để tránh lặp code.

    Args:
        text: Câu hỏi hoặc nội dung cần tìm kiếm.

    Returns:
        Một vector embedding đã chuẩn hóa.

    Ví dụ trong RAG:
        Người dùng hỏi:
            "Điều kiện thành lập doanh nghiệp là gì?"

        Hàm chuyển câu hỏi thành vector để Qdrant tìm kiếm
        các đoạn tài liệu có nội dung liên quan.
    """
    # Đưa câu truy vấn vào danh sách gồm một phần tử.
    # embed_texts() trả về danh sách vector nên [0] lấy vector đầu tiên.
    return embed_texts([text])[0]