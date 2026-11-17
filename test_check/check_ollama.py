# Thư viện requests dùng để gửi HTTP request đến API của Ollama.
import requests

# Import các biến cấu hình từ file config.py:
# - EMBEDDING_MODEL: Model dùng để chuyển văn bản thành vector embedding.
# - GENERATION_MODEL: Model dùng để sinh câu trả lời.
# - normalize_ollama_base_url: Địa chỉ Ollama đã bỏ /v1 thừa (nếu có).
from config import EMBEDDING_MODEL, GENERATION_MODEL, normalize_ollama_base_url


# Gửi HTTP GET request đến endpoint /api/tags của Ollama.
# Endpoint này trả về danh sách các model hiện có trên máy.
# timeout=10: Tối đa chờ 10 giây cho request.
response = requests.get(
    f'{normalize_ollama_base_url()}/api/tags',
    timeout=10
)

# Kiểm tra HTTP status code của response.
# Nếu request thất bại (ví dụ: 404 hoặc 500), chương trình sẽ phát sinh exception.
# Nếu Ollama không kết nối được hoặc hết thời gian chờ, requests cũng có thể phát sinh exception.
response.raise_for_status()

# Chuyển dữ liệu JSON nhận được thành đối tượng Python.
# Lấy danh sách model từ trường 'models'.
# Với mỗi model, lấy giá trị 'name' để biết tên model đã cài đặt.
# Ví dụ: ['bge-m3:latest', 'qwen3:14b']
installed = [
    m['name']
    for m in response.json()['models']
]

# In danh sách tên các model đang có trên Ollama.
print('Model đã cài:', installed)


# Lần lượt kiểm tra hai model được khai báo trong config.py:
# - Model embedding.
# - Model sinh câu trả lời.
for wanted in (EMBEDDING_MODEL, GENERATION_MODEL):

    # Kiểm tra model cần dùng có trong danh sách đã cài hay không.
    #
    # Điều kiện 1:
    # name == wanted
    # Tên model khớp hoàn toàn.
    #
    # Điều kiện 2:
    # name.startswith(wanted + ':')
    # Tên model bắt đầu bằng tên cần tìm và theo sau là dấu ':'.
    # Điều này cho phép khớp các tag như ':latest' hoặc ':14b'.
    #
    # Ví dụ:
    # wanted = 'bge-m3'
    # name = 'bge-m3:latest'
    # => Khớp vì name bắt đầu bằng 'bge-m3:'.
    ok = any(
        name == wanted or name.startswith(wanted + ':')
        for name in installed
    )

    # In kết quả kiểm tra:
    # - OK: Đã tìm thấy model.
    # - THIẾU: Chưa tìm thấy model phù hợp, gợi ý lệnh tải model.
    print(
        wanted,
        ': OK' if ok else ': THIẾU - chạy ollama pull ' + wanted
    )