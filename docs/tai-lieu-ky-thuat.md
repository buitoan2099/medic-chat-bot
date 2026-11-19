# Tài liệu kỹ thuật: hệ thống đã triển khai

Cập nhật: 19/11/2026 · Dành cho: người phát triển và vận hành

Tài liệu này mô tả **hệ thống đúng như đang chạy**. Bản thiết kế gốc nằm ở [chat-3-khung/](chat-3-khung/README.md); mục 9 liệt kê những chỗ đã làm khác thiết kế. Hướng dẫn cho người dùng cuối nằm ở [huong-dan-su-dung.md](huong-dan-su-dung.md). Báo cáo cải tiến phần RAG nằm ở [../BAO_CAO_CAI_TIEN.md](../BAO_CAO_CAI_TIEN.md).

## 1. Hiện trạng

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| P0 | git, pytest, backend FastAPI, lớp lưu trữ | ✅ commit `76ae76b` |
| P1 | Khung 1 (AI + phân loại), trang cấu hình model, chỉ mục blue-green | ✅ commit `76ae76b` |
| P2 | Khung 2: người trực, cấp C1–C3, gợi ý theo cấp, chuyển, đẩy cấp, SLA | ✅ commit `04af971` |
| P3 | Khung 3: trợ lý quản lý AG-7, số liệu, form F-1…F-5, phân quyền | ✅ commit `876a05a` |
| Sau P3 | Tài khoản thử, tự cuộn, loading, gợi ý tự hiện, F-6, thay người trực giữa chừng, bỏ kiểm tra trước khi gửi, hàng đợi LLM có giữ chỗ, chống tạo trùng gợi ý | ⏳ **chưa commit** |
| P4 | Bộ quy tắc phân tầng, danh mục thuốc kê đơn (Q-2), bộ test có nhãn cho agent | ⏸ chờ Hội đồng / dữ liệu |
| Zalo | Kết nối Zalo qua zca-js | 📝 kế hoạch: [chat-3-khung/09-ket-noi-zalo.md](chat-3-khung/09-ket-noi-zalo.md) |

Kiểm thử: **149 test** pytest, chạy khoảng 40 giây, không cần Ollama hay Qdrant.

## 2. Kiến trúc

```
Trình duyệt ─► Streamlit (ui/)  ──HTTP/SSE──►  FastAPI backend (backend/, 1 worker)
                Home · Người trực · Quản lý         ├─ dịch vụ: chat, operator, copilot, guard, triage,
                Phân quyền · Cấu hình model         │           manager_agent, metrics, permissions…
                                                     ├─ LLMGateway ─► Ollama (qwen3:14b, bge-m3)
                                                     │              (hàng đợi ưu tiên, dự phòng, ngắt mạch)
                                                     ├─ Qdrant embedded (qdrant_db/)  ← CHỈ backend mở
                                                     └─ lưu trữ local theo ngày (storage/)
```

Quy tắc bắt buộc:
- **R1/R2:** backend là **tiến trình duy nhất** mở Qdrant (`qdrant_db/`) và ghi `storage/`. Luôn chạy `--workers 1`, không dùng `--reload`.
- `app.py`, `python -m rag.ingest` và eval không có `--api` **không được chạy cùng lúc** với backend.
- Qdrant embedded không an toàn khi nhiều thread cùng ghi (đã gặp mất 12/200 điểm), nên mọi lời gọi đi qua `LockedClient` trong `backend/services/index_manager.py`.
- UI chỉ nói chuyện với backend qua `BACKEND_URL` (`ui/api_client.py`).

## 3. Chạy hệ thống

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock -r requirements-dev.txt
cp .env.example .env                       # sửa OLLAMA_BASE_URL, ADMIN_TOKEN, AUTH_SECRET
python -m rag.ingest --reset               # tạo chỉ mục lần đầu (backend phải TẮT); hoặc làm trên trang Cấu hình model
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1    # terminal 1
streamlit run ui/Home.py                                             # terminal 2
pytest                                                               # test
```

Biến môi trường chính (`.env`):

| Biến | Ý nghĩa |
|---|---|
| `OLLAMA_BASE_URL`, `EMBEDDING_MODEL`, `GENERATION_MODEL` | Máy Ollama, model embedding (`bge-m3`), model sinh (`qwen3:14b`) |
| `COLLECTION_NAME` | Bộ chỉ mục đang dùng (hiện tại `duoc_2018_v2`) |
| `TOP_K`, `CANDIDATE_K`, `MIN_SCORE` | Tham số truy xuất (giá trị khởi tạo; về sau chỉnh trong cài đặt) |
| `STORAGE_DIR`, `QDRANT_DIR` | Thư mục dữ liệu |
| `BACKEND_URL` | Địa chỉ backend mà UI gọi |
| `ADMIN_TOKEN` | Khoá vào trang Cấu hình model và API `/api/admin` |
| `AUTH_SECRET` | Khoá ký token đăng nhập (đổi khoá thì mọi phiên đăng xuất) |
| `DEMO_MODE` | `true` = có tài khoản thử đăng nhập không cần mật khẩu. **Chạy thật phải để `false`** |
| `LLM_PROVIDER`, `GEMINI_*`, `OPENAI_*` | Nhà cung cấp LLM khác (tuỳ chọn) |

Công cụ dòng lệnh:
- `scripts/staff.py`: quản lý nhân sự qua API admin.
- `scripts/bench_ollama.py`: đo tốc độ Ollama. Báo cáo không ghi địa chỉ máy chủ.
- `evaluation/run_eval.py`: đánh giá truy xuất; thêm `--api` để chạy khi backend đang chạy.

## 4. Cấu trúc mã nguồn

| Thư mục / file | Nội dung |
|---|---|
| `rag/` | Phân tích PDF tổng quát (`pdf_parser.py`), tạo chỉ mục (`ingest.py`, có resume), truy xuất vector + BM25 + RRF (`rag.py`, `lexical.py`), embedding (`embeddings.py`), tiến độ (`progress.py`) |
| `backend/main.py` | Dựng ứng dụng (`build_state`), executor nền 4 luồng, `/api/health` |
| `backend/domain.py` | Mô hình dữ liệu pydantic |
| `backend/storage/` | Interface repository (`base.py`) và bản lưu local (`local.py`) |
| `backend/llm/gateway.py` | Adapter Ollama / OpenAI-compatible / giả lập; hàng đợi ưu tiên; dự phòng; ngắt mạch |
| `backend/agents/` | Danh mục agent (`registry.py`), ngân sách ngữ cảnh (`context_builder.py`), lược đồ JSON (`schemas.py`) |
| `backend/services/` | Nghiệp vụ (bảng mục 6) |
| `backend/api/` | Router: `chat` (khung 1), `operator` (khung 2), `manager` (khung 3), `admin` |
| `ui/` | `Home.py`, `pages/1_Nguoi_truc.py`, `2_Quan_ly.py`, `3_Phan_quyen.py`, `9_Cau_hinh_model.py`; dùng chung: `api_client.py`, `staff_login.py`, `scroll.py` (tự cuộn + dòng chờ có đồng hồ) |
| `prompts/agents/agX/v1.txt` | Prompt khởi tạo. Prompt đang dùng nằm trong `storage/config/prompts`, có phiên bản |
| `rules/` | `emergency_minimal.json` (dấu hiệu cấp cứu), `prescription_drugs.json` (**đang rỗng**, chờ Q-2) |
| `tests/` | Test RAG/parser và `tests/backend/` (API từng giai đoạn, lưu trữ, gateway, số liệu, quyền, tài khoản thử) |

## 5. Agent và hàng đợi LLM

| Agent | Ưu tiên | Timeout | Kích hoạt khi |
|---|---|---|---|
| AG-0 phân loại | 1 | 45 s | Mỗi tin ở chế độ AI. Quy tắc cấp cứu chạy trước; LLM lỗi thì mặc định an toàn (chuyển người trực) |
| AG-1 trả lời AI | 2 | 300 s | Câu hỏi được phép trả lời; trả về dạng stream |
| AG-6 kiểm tra trước khi gửi | 2 | 90 s | **Chỉ khi** `guard_llm_enabled = true` |
| AG-2/3/4 gợi ý theo cấp | 3 | 300 s | Khi tiếp nhận, khi được chỉ định, khi khách nhắn, khi bấm tạo lại |
| AG-7 quản lý | 4 | 300 s | Câu hỏi ở khung 3 (gọi công cụ, tối đa 5 vòng) |
| AG-5 hồ sơ ca | 5 | 180 s | Khi chuyển sang người trực, và **sau khi gợi ý xong** mỗi lần khách nhắn |

Hàng đợi `PriorityLimiter`:
- `llm_max_parallel` yêu cầu chạy cùng lúc; ai chờ thì theo ưu tiên, cùng ưu tiên thì đến trước được trước.
- `llm_reserved_slots` giữ chỗ cho việc ưu tiên 1–2: việc nền (≥ 3) không chiếm hết chỗ. Chỉ có tác dụng khi `llm_max_parallel ≥ 2`.
- Mỗi lần gọi ghi `duration_s` và `queue_wait_s` (thời gian xếp hàng) vào `storage/ai/…/runs.jsonl`.

Chống lãng phí khi tạo gợi ý:
- Đã có gợi ý (chưa dùng) cho đúng tin mới nhất của khách thì không tạo lại.
- Có lượt mới hơn đang xếp hàng thì bỏ lượt cũ.
- Bấm "tạo lại kèm chỉ dẫn" thì luôn tạo.

Số đo trên Mac mini (18–19/11/2026, `qwen3:14b`, ctx 16k):
- Ollama xử lý **tuần tự** các yêu cầu.
- Đọc prompt khoảng 100–117 token/giây; sinh chữ khoảng 9–11 token/giây.
- Phân loại 12–20 giây; câu trả lời AI có chữ đầu sau khoảng 38 giây; gợi ý 40–70 giây; hồ sơ ca 20–30 giây.
- Ước lượng phục vụ được khoảng **3–5 người trực** cùng lúc.

## 6. Nghiệp vụ chính và nơi cài đặt

| Quy tắc | Nơi cài | Ghi chú |
|---|---|---|
| Hàng chờ chỉ hiện ca đủ cấp; ca khẩn trước (BR-02) | `operator_service.queue` | |
| Tiếp nhận có khoá: hai người bấm cùng lúc thì chỉ một người được (BR-01) | `operator_service.claim` + `mutate` (khoá lạc quan, thử lại) | Chỉ tài khoản có vai trò `operator` |
| Quản lý chỉ định ca **đang chờ hoặc đang xử lý** (BR-03) | `operator_service.assign` | Có thể nâng `required_level`; báo khách; giao cho người chưa đủ cấp thì cần `override_level` và lý do |
| Chuyển cần người nhận chấp nhận | `request_transfer` / `respond_transfer` | |
| Đẩy cấp: về hàng chờ với cấp cao hơn | `escalate` | |
| Cảnh báo chờ quá SLA (BR-05) | `SlaMonitor` | |
| Nhắn lại ≤ 24 giờ thì mở lại cho người cũ; quá hạn thì mở cuộc chat mới có liên kết (BR-06) | `customer_message` | |
| **Gửi tin của người trực** | `operator_service.send` + `guard.check` | Mặc định không gọi AG-6: chỉ quy tắc (danh mục thuốc kê đơn thì chặn, trích dẫn thì cảnh báo) |
| **Gợi ý vượt quyền không gửi được** | `operator_service.send` | Dựa vào `scope_check = exceeds` của gợi ý; nguyên văn hay đã sửa đều bị chặn |
| Gửi nguyên gợi ý cần quyền `ai.send_unedited` (AC-2.9) | `send` | |
| Số liệu do code tính, AI chỉ viết nhận định (BR-11) | `metrics.py`, `forms.py` | F-1…F-6 |
| AG-7 chỉ đọc; thao tác ghi = đề xuất cần xác nhận (BR-10) | `manager_agent.py` | |
| Nâng C2/C3 cần chứng chỉ đã xác minh | `permissions.grant` | |

Quyền chi tiết (`CAPABILITY_DEFAULTS`): `chat.claim`, `chat.transfer`, `chat.escalate`, `chat.view_all`, `ai.use_copilot`, `ai.send_unedited`, `chat.max_concurrent` (mặc định 5). Vai trò: `operator`, `manager`, `admin`.

Đăng nhập:
- Mật khẩu băm bằng scrypt; token ký HMAC bằng `AUTH_SECRET`; sai nhiều lần thì khoá tạm.
- `DEMO_MODE` tạo `demo_c1/c2/c3` (người trực) và `demo_quanly` (chỉ quản lý). Đăng nhập một chạm chỉ áp dụng cho tài khoản `demo_*`, có ghi nhật ký.
- UI giữ **phiên riêng cho từng khung**: `op_token` cho người trực, `mgr_token` cho quản lý.

## 7. Dữ liệu

```
storage/
  conversations/<id>.json            cuộc chat (bản hiện hành, có version cho khoá lạc quan)
  messages/YYYY/MM/DD/…              tin nhắn + sự kiện (_events.jsonl), chia theo ngày giờ VN
  ai/YYYY/MM/DD/runs.jsonl           mỗi lần gọi LLM: agent, model, thời gian, token, lỗi
  ai/YYYY/MM/DD/suggestions.jsonl    gợi ý + kết quả sử dụng (gửi nguyên / sửa / bỏ / thay thế)
  ai/YYYY/MM/DD/guard_checks.jsonl   kết quả kiểm tra trước khi gửi
  users/staff.jsonl                  nhân sự (chỉ ghi thêm, bản mới nhất là hiện hành)
  permissions/ presence/ audit/      cấp quyền, trạng thái trực, nhật ký thao tác
  manager/                           phiên và tin của khung quản lý, đề xuất
  config/                            cấu hình agent, prompt có phiên bản, cài đặt
```

- Mã định danh là **ULID**: 26 ký tự, sắp được theo thời gian, mang ngày tạo. Thư mục ngày tính theo giờ Việt Nam.
- Mọi truy cập đi qua interface trong `backend/storage/base.py`. Muốn chuyển sang DB thì viết thêm một bản cài đặt; `tests/backend/test_storage_contract.py` là bộ test hợp đồng dùng chung.
- `.gitignore` loại `.env`, `qdrant_db/`, `storage/`, `data/documents/` (PDF không đưa lên git vì bản quyền).

## 8. API

Tài liệu tương tác: `http://127.0.0.1:8000/docs` (Swagger do FastAPI tạo).

| Nhóm | Tiền tố | Xác thực | Chính |
|---|---|---|---|
| Khung 1 | `/api/chat` | (mã cuộc chat) | tạo cuộc chat, gửi tin (**SSE**: `message`, `status` = classifying / searching / generating, `triage`, `token`, `done`, `error`), chuyển người trực, hồ sơ |
| Khung 2 | `/api/operator` | Bearer token | đăng nhập, `demo-accounts`, `demo-login`, trạng thái trực, hàng chờ, xem / tiếp nhận / gửi / kiểm tra / tạo lại gợi ý / chuyển / đẩy cấp / đóng |
| Khung 3 | `/api/manager` | Bearer + vai trò `manager` | phiên, `ask`, `quick` (today, week, compare_today, sla, waiting, operator, **workday**, conversation), xác nhận đề xuất, `board` (có `assigned_items`), `assign`, nhân sự / quyền / chứng chỉ / mẫu, bật tắt agent |
| Quản trị | `/api/admin` | `X-Admin-Token` | agent, prompt (phiên bản, kích hoạt, thử), cài đặt, chỉ mục (rebuild / resume / cancel / rollback), tìm kiếm thử, nhân sự |
| Sức khoẻ | `/api/health` | — | `qdrant_open`, `vectors_ready`, `index_job_running`, `llm_queue` |

`GET /api/operator/conversations/{id}` trả thêm `suggestion_pending_since` (đang tạo gợi ý từ lúc nào), để UI hiện dòng chờ.

## 9. Khác biệt so với đặc tả

| Điểm | Đặc tả | Đã làm | Lý do |
|---|---|---|---|
| Kiểm tra trước khi gửi (AG-6) | Mọi tin đều qua AG-6 | **Tắt mặc định** (`guard_llm_enabled`); chỉ còn quy tắc | Người dùng yêu cầu gửi ngay; AG-6 phải xếp hàng sau gợi ý (đến hàng chục giây). **Hệ quả:** danh mục thuốc kê đơn rỗng thì không chặn được thuốc kê đơn trong tin tự soạn |
| Lỗi vượt quyền | Xác nhận kèm lý do | Gợi ý vượt quyền: **chặn**. Tin tự soạn: không chặn | Theo yêu cầu "người trực trả lời thoải mái, chỉ chặn gợi ý không có quyền" |
| Số yêu cầu LLM song song | 2 | 1 | Đo được Ollama trên Mac mini xử lý tuần tự |
| AG-5 hồ sơ ca | Sau mỗi tin khách | Khi chuyển người trực, và sau khi gợi ý xong | Không chiếm Ollama trước gợi ý |
| Chỉ định | Ca đang chờ | Cả ca **đang xử lý**, có nâng cấp | Thay người trực không đủ thẩm quyền giữa chừng |
| Form quản lý | F-1…F-5 | Thêm **F-6** nội dung đã xử lý | Quản lý cần biết người trực đã tư vấn gì |
| Tài khoản thử | — | `DEMO_MODE` | Phục vụ trình diễn |
| Trọng số BM25 | Như nhau | Câu có dấu 0.0, câu không dấu 1.0 | Đo bằng eval: BM25 với câu có dấu làm kết quả kém đi |

Các quyết định kiến trúc đã chốt nằm ở [chat-3-khung/07-xung-dot-kien-truc.md](chat-3-khung/07-xung-dot-kien-truc.md):
- giữ Qdrant embedded trong một tiến trình;
- FastAPI làm backend, Streamlit làm client;
- giữ Ollama với ctx 16k;
- không kê đơn trực tuyến.

## 10. Hạn chế và việc còn mở

- **Tốc độ:** gợi ý mất khoảng 1 phút; câu trả lời AI có chữ đầu sau khoảng 38 giây. Các hướng giảm:
  - model nhỏ hơn cho gợi ý / AG-0 / AG-5;
  - đặt `OLLAMA_NUM_PARALLEL=2` và `llm_max_parallel=2` (giữ chỗ cho việc gấp có tác dụng);
  - thêm phần cứng.
- **Danh mục thuốc kê đơn** (`rules/prescription_drugs.json`) còn rỗng, chờ Q-2. Đây là chốt chặn duy nhất cho thuốc kê đơn khi AG-6 tắt.
- **Bộ quy tắc phân tầng** (`tiering_rules_enabled`) chờ Hội đồng duyệt ([../phan-tang.md](../phan-tang.md)).
- **Chưa có bộ test có nhãn** để đo chất lượng từng agent (AC-5.x).
- **Bảng benchmark song song** trong `docs/benchmarks/ollama-20261118-2035.md` không hợp lệ (do cache prompt); cần đo lại bằng script đã sửa.
- **Một tiến trình:** lưu trữ là file local và Qdrant embedded, nên không chạy được nhiều backend. Muốn mở rộng thì chuyển sang DB và Qdrant server (đã có lớp repository để chuẩn bị).
- **Chưa có thông báo đẩy** (push): UI tự làm mới 3 giây (khung 1, 2) và 10 giây (bảng trạng thái quản lý).
