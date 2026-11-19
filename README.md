# Medic Chat Bot – Tra cứu Dược thư Quốc gia

Chatbot hỏi đáp (RAG) trên tài liệu PDF. Hiện dùng cho **Dược thư Quốc gia Việt Nam 2018**.

- Đọc PDF, tự nhận diện tiêu đề và mục, chia nội dung thành các đoạn (chunk).
- Tìm kiếm kết hợp vector (Qdrant + bge-m3 qua Ollama) và từ khoá (BM25).
- Sinh câu trả lời bằng Ollama, Gemini hoặc OpenAI-compatible, có streaming.
- Giao diện Streamlit.

## Cài đặt

**Yêu cầu:** Python 3.13, Ollama có model `bge-m3` (embedding) và model sinh văn bản (mặc định `qwen3:14b`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock        # phiên bản đã kiểm thử (hoặc requirements.txt)
pip install -r requirements-dev.txt     # pytest
cp .env.example .env        # rồi sửa OLLAMA_BASE_URL, khoá API (nếu dùng)
python -m test_check.check_ollama   # kiểm tra kết nối và model
```

## Tài liệu PDF (không có trong repo)

Vì lý do bản quyền, file PDF **không** được đưa vào repo. Hãy tải về và đặt đúng đường dẫn:

```
data/documents/duoc-thu-quoc-gia-viet-nam-2018.pdf
```

- **Nguồn tải (bản do bên thứ ba lưu trữ, không phải nguồn chính thức của Bộ Y tế):**
  https://bvranghammat.com/wp-content/uploads/2023/09/duoc-thu-quoc-gia-viet-nam-2018.pdf
- **Kiểm tra đúng file** với bản đã dùng để phát triển và đánh giá:
  - Kích thước: 38.795.771 byte (~37 MB), 1.668 trang
  - SHA-256: `2aa81c846a5e760f82658c46816ab63174204a7d95b3e2755b6565288e53d0d1`

  ```bash
  shasum -a 256 data/documents/duoc-thu-quoc-gia-viet-nam-2018.pdf
  ```

  Nếu mã khác (do nguồn đã đổi file), bộ đánh giá trong `evaluation/` có thể không còn khớp số trang.

- **Bản quyền:** Dược thư Quốc gia Việt Nam là ấn phẩm của Bộ Y tế. File chỉ dùng cho mục đích nghiên cứu, phát triển nội bộ. Không phân phối lại file hay toàn văn nội dung. Trước khi vận hành cho người dùng thật cần có xác nhận của Pháp chế hoặc sự cho phép của đơn vị giữ bản quyền.

Muốn dùng tài liệu khác thì đặt PDF vào `data/documents/` và sửa `PDF_GLOB`, `COLLECTION_NAME`, `APP_TITLE`… trong `.env`.

## Lập chỉ mục và chạy

```bash
python -m rag.ingest --dry-run   # chỉ phân tích PDF, xem trước chunks (không cần Ollama)
python -m rag.ingest --reset     # tạo chỉ mục (cần Ollama, ~16.160 chunks) – chạy khi backend TẮT
```

**Chạy hệ thống (từ P1):** hai tiến trình, backend trước rồi giao diện.

```bash
# 1) Backend FastAPI – tiến trình DUY NHẤT mở Qdrant (luôn 1 worker, không --reload)
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1

# 2) Giao diện Streamlit (khung 1 + trang cấu hình model), gọi backend qua BACKEND_URL
streamlit run ui/Home.py
```

- Trang **Cấu hình model** cần `ADMIN_TOKEN` trong `.env`. Trên trang này có: chọn model cho từng agent, phiên bản prompt, cài đặt, dựng lại chỉ mục **không gián đoạn** (dựng song song rồi mới chuyển sang).
- Không có Ollama thì hệ thống vẫn chạy: tìm tài liệu bằng BM25, còn câu hỏi được chuyển sang người trực theo mặc định an toàn.
- **Người trực (P2):** trang *Người trực* trong giao diện. Tạo tài khoản khi backend đang chạy:
  ```bash
  python -m scripts.staff create lan "Nguyễn Lan" --title "Dược sĩ"
  python -m scripts.staff credential lan --kind duoc_si --expires 2030-12-31 --verify
  python -m scripts.staff grant lan level C2 --reason "Đã xác minh chứng chỉ"
  ```
  Cần `AUTH_SECRET` trong `.env` để phiên đăng nhập không mất khi khởi động lại backend.
- **Tài khoản thử:** đặt `DEMO_MODE=true` trong `.env` thì backend tạo sẵn `demo_c1` (Điều dưỡng, C1), `demo_c2` (Dược sĩ, C2), `demo_c3` (Bác sĩ, C3), `demo_quanly` (chỉ quản lý, không nhận chat); màn đăng nhập cho chọn tài khoản, không cần mật khẩu. Mỗi khung một phiên riêng: trang *Người trực* chỉ liệt kê tài khoản người trực, trang *Quản lý*/*Phân quyền* chỉ liệt kê tài khoản quản lý. **Vận hành thật phải để `DEMO_MODE=false`.**
- **Quản lý (P3):** trang *Quản lý* (chat với agent quản lý, báo cáo nhanh, bảng trạng thái, ⚡ điều chỉnh nhanh) và trang *Phân quyền* (chứng chỉ, cấp chuyên môn, quyền thao tác, lịch sử). Tài khoản cần vai trò `manager`: `python -m scripts.staff create quanly "Tên" --roles operator,manager`.
- `app.py` là giao diện cũ (một trang, tự mở Qdrant). **Không chạy cùng lúc với backend.** Sẽ bỏ khi hết P1.

## Kiểm thử

```bash
pytest                     # unit test + hồi quy (không cần Ollama/Qdrant)
pytest -m "not corpus"     # bỏ test hồi quy trên Dược thư thật
```

Test hồi quy `corpus` cần cache trích xuất PDF (`qdrant_db/cache/`, sinh bởi `rag.ingest --dry-run`); thiếu thì tự bỏ qua.

## Đo năng lực Ollama

```bash
python -m scripts.bench_ollama      # kết quả: docs/benchmarks/ollama-<thời điểm>.md
```

## Đánh giá truy xuất

```bash
python -m evaluation.run_eval                 # baseline / dense / bm25 / hybrid
python -m evaluation.run_eval --methods bm25  # không cần Ollama
python -m evaluation.run_eval --api           # khi backend đang chạy
```

## Tài liệu dự án

- [docs/huong-dan-su-dung.md](docs/huong-dan-su-dung.md) – hướng dẫn cho người trực, quản lý, quản trị
- [docs/tai-lieu-ky-thuat.md](docs/tai-lieu-ky-thuat.md) – hệ thống đã triển khai: kiến trúc, chạy, cấu hình, API, dữ liệu, khác biệt so với đặc tả
- [BAO_CAO_CAI_TIEN.md](BAO_CAO_CAI_TIEN.md) – các cải tiến RAG và kết quả đánh giá
- [docs/chat-3-khung/](docs/chat-3-khung/README.md) – đặc tả và technical plan hệ thống chat 3 khung
- [docs/phan-tang.md](docs/phan-tang.md) – phân tầng ca bệnh, danh mục chuyên môn (chờ Hội đồng duyệt)
