# 08 · Technical plan

Ngày: 17/11/2026 · Đầu vào: đặc tả 01–06, [phan-tang.md](../phan-tang.md), báo cáo xung đột và quyết định ở [07](07-xung-dot-kien-truc.md).

## 1. Quyết định nền

| Mã | Quyết định | Nguồn |
|---|---|---|
| Q-A | Giữ Qdrant **embedded**; backend là tiến trình **duy nhất** truy cập | 07 |
| Q-B | **FastAPI** backend + **Streamlit** client | 07 |
| Q-C | Rebuild chỉ mục **xanh–lục ở mức ứng dụng** | 07 (suy ra từ Q-A) |
| Q-D | **Ollama** trên Mac mini, `NUM_CTX` **16k**, ngân sách ngữ cảnh có kiểm soát | 07 |
| Q-E | **git + pytest** trước khi tái cấu trúc | 07 |
| — | Không kê đơn trực tuyến; C2 chỉ tư vấn thuốc không kê đơn; C3 tư vấn + hẹn khám | phan-tang.md |
| — | Dữ liệu chat **không ra ngoài**: mọi agent mặc định dùng Ollama. Provider cloud vẫn có trong code nhưng **tắt** trên trang cấu hình, chỉ bật khi được duyệt (Q-5). | Hệ quả của Q-D |

## 2. Kiến trúc đích

```
┌──────────────── Tiến trình UI (Streamlit, nhiều trang) ─────────────────┐
│ Khung 1 · Khung 2 · Khung 3 · Cấu hình model · Phân quyền                 │
│ Chỉ gọi HTTP tới backend (httpx). Làm mới bằng st.fragment(run_every).   │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ REST + SSE (+ WebSocket cho web app sau này)
┌──────────────────────────────▼───────────────────────────────────────────┐
│ Tiến trình BACKEND (FastAPI, uvicorn --workers 1) – DUY NHẤT mở Qdrant    │
│                                                                           │
│  api/        auth · end-user chat · operator · manager · admin · sync     │
│  services/   Conversation · Messaging · Triage · Copilot · Guard ·        │
│              CaseMemory · ManagerAgent · Metrics · Permission · Config    │
│  agents/     AgentRegistry (prompt có phiên bản) · ContextBuilder ·       │
│              lược đồ đầu ra · công cụ AG-7                                 │
│  llm/        LLMGateway: nhiều lượt, đầu ra có cấu trúc, gọi công cụ,     │
│              streaming, HÀNG ĐỢI ƯU TIÊN + giới hạn song song             │
│  rules/      Bộ quy tắc phân tầng (T1/T2/T3, danh sách OTC) có phiên bản  │
│  storage/    Repository (local theo ngày → DB sau này)                    │
│  rag/        (code hiện có) retrieve · BM25 · ingest · IndexManager       │
│  workers/    tác vụ nền: tóm tắt ca (AG-5) · SLA · ingest · sao lưu       │
│  events/     bus sự kiện trong tiến trình → SSE/sync                      │
└──────────────┬───────────────────────────┬───────────────────────────────┘
               │                           │
      Qdrant embedded + BM25        Ollama (Mac mini, Tailscale)
      (qdrant_db/, trong tiến trình) bge-m3 (embedding) · qwen3:14b (sinh)
```

**Quy tắc bất biến:**
- **R1:** Chỉ backend import `qdrant_client`, `rag.*`, `llm.*`. UI và script chỉ gọi API.
- **R2:** Backend chạy **1 worker**. Không bật `--reload` hay nhiều worker ở production. Có kiểm tra lúc khởi động: nếu Qdrant báo đang bị khoá thì backend dừng, kèm thông báo rõ ràng.
- **R3:** Mọi lời gọi LLM đi qua `LLMGateway`, không gọi provider trực tiếp.
- **R4:** Nội dung chuyên môn (prompt, rule set, danh sách OTC) là **dữ liệu có phiên bản**, không viết cứng trong code.

## 3. Giải quyết từng xung đột

| Mã | Thay đổi | Module |
|---|---|---|
| X-1 | `rag/rag.py` giữ cơ chế client dùng chung nhưng chỉ chạy trong backend. Bỏ `pause/resume` dùng cho tiến trình con. Ingest chạy **trong** backend (luồng nền) dùng chung client. `test_check/` và `evaluation/` chuyển sang gọi API admin; chế độ offline chỉ chạy khi backend tắt (script tự kiểm tra khoá). | `rag/`, `backend/api/admin`, `evaluation/` |
| X-2 | Tách nghiệp vụ khỏi `app.py` vào `backend/services`. `app.py` cũ thay bằng `ui/` nhiều trang. Trạng thái dùng chung nằm trong repository; khoá tiếp nhận dùng `version` (khoá lạc quan) trong tiến trình backend duy nhất. | `backend/`, `ui/` |
| X-3 | `IndexManager`: con trỏ `active_collection` (lưu trong cấu hình). Rebuild = ingest vào collection mới `<base>_<timestamp>` cùng sidecar BM25 riêng, chạy đánh giá nhanh, rồi chuyển con trỏ nguyên tử. Giữ 1 bản cũ để quay lại. `--reset` chỉ còn trong chế độ offline. **Lưu ý RAM:** khi dựng song song, Qdrant embedded giữ hai collection trong bộ nhớ (~2 × 65 MB vector + payload), chấp nhận được. | `rag/ingest.py`, `backend/rag/index_manager` |
| X-4 | `LLMGateway` thay `provider/llm.py`. Giao diện chung: `messages[]` + `AgentConfig` + (tuỳ chọn) lược đồ đầu ra + (tuỳ chọn) công cụ + streaming. Ollama dùng `/api/chat` với `format` (JSON schema) cho đầu ra có cấu trúc và `tools` cho AG-7 (qwen3 hỗ trợ). Gemini/OpenAI giữ adapter tương ứng nhưng tắt mặc định. Giữ `ThinkFilter`. | `backend/llm/` |
| X-5 | `config.py` chỉ còn **cấu hình khởi động** (đường dẫn, URL Ollama, khoá bí mật). Cấu hình vận hành (agent → model/tham số/phiên bản prompt, SLA, ngưỡng, `active_collection`) do `ConfigService` đọc từ `storage/config/` mỗi lần dùng (có cache ngắn, xoá cache khi lưu). | `config.py`, `backend/services/config` |
| X-6 | `NUM_CTX = 16384`. `ContextBuilder` cắt theo **ngân sách token** (mục 5.2), ước lượng token bảo thủ và hiệu chỉnh bằng `prompt_eval_count` Ollama trả về. Vượt ngân sách thì cắt theo thứ tự ưu tiên, không để Ollama cắt im lặng. | `backend/agents/context_builder` |
| X-7 | Hàng đợi ưu tiên + giới hạn song song trong `LLMGateway` (mục 5.3). Một model sinh duy nhất cho mọi agent để tránh nạp/thay model. AG-0 chạy **quy tắc trước**, LLM sau. Đo năng lực thật ở P0 rồi chốt NFR. | `backend/llm/`, `backend/services/triage` |
| X-8 | Một tiến trình ghi duy nhất (R1/R2), nên khoá trong tiến trình (`asyncio.Lock` theo `conversation_id`) là đủ. Công cụ dựng lại chỉ mục / chuyển dữ liệu chạy khi backend tắt, hoặc qua API admin. | `backend/storage/` |
| X-9 | `retrieve()` nhận thêm `query_override` (truy vấn do ContextBuilder dựng từ câu hỏi + hồ sơ ca + tóm tắt) và `collection`. Copilot gọi với `min_score=None` (luôn có ngữ cảnh, kèm cờ "độ liên quan thấp"). Chế độ AI giữ ngưỡng. | `rag/rag.py` |
| X-10 | P0: git, `.gitignore`, ghim phiên bản, pytest. | toàn repo |

## 4. Cấu trúc thư mục đích

```
chatbot/
├── backend/
│   ├── main.py                 khởi tạo app, kiểm tra khoá Qdrant, nạp BM25, khởi động workers
│   ├── api/                    routers: auth, enduser, operator, manager, admin, sync
│   ├── services/               nghiệp vụ (mục 3, đặc tả 01)
│   ├── agents/                 registry, context_builder, schemas, tools (AG-7)
│   ├── llm/                    gateway, adapters (ollama, gemini, openai), queue
│   ├── rules/                  nạp & đánh giá rule set phân tầng, danh sách OTC
│   ├── storage/                interfaces + local/ (+ postgres/ sau này)
│   ├── workers/                case_memory, sla_monitor, ingest_job, backup
│   ├── events/                 bus sự kiện + SSE
│   └── domain/                 mô hình dữ liệu (pydantic), enum trạng thái, quyền
├── rag/                        (hiện có) pdf_parser, lexical, embeddings, ingest, rag + index_manager
├── ui/                         Streamlit: Home (khung 1), pages/ khung 2, khung 3, model, phân quyền
│   └── api_client.py           client HTTP duy nhất UI dùng
├── prompts/agents/<agent>/v<N>.txt   prompt khởi tạo (sao chép vào storage/config khi khởi tạo)
├── rules/                      rule set khởi tạo (chỉ bật khi đã duyệt – feature flag)
├── storage/                    dữ liệu chạy (gitignore)
├── tests/                      unit · integration (API) · contract (repository) · agent eval
├── evaluation/                 (hiện có) chuyển sang gọi API
└── docs/
```

`provider/` sẽ được gộp vào `backend/llm/`. `app.py` được thay bằng `ui/`, và giữ lại tới hết P1 để đối chiếu.

## 5. Thiết kế chi tiết các điểm khó

### 5.1 API chính (theo nhóm)

| Nhóm | Endpoint (tóm tắt) | Người gọi |
|---|---|---|
| auth | đăng nhập nhân sự (JWT), cấp token ẩn danh cho người dùng | UI |
| enduser | tạo cuộc chat, chọn chế độ, gửi tin (AI trả về **SSE stream**), chuyển sang người trực, lịch sử theo ngày, đánh giá | Khung 1 |
| operator | hàng chờ, tiếp nhận, cuộc chat của tôi, gửi tin (qua Guard), gợi ý (SSE), tạo lại gợi ý, chuyển, đẩy cấp, đóng, trạng thái trực, sửa hồ sơ ca | Khung 2 |
| manager | chat với AG-7 (SSE), xác nhận/huỷ đề xuất, bảng trạng thái, xem cuộc chat, chỉ định, thao tác nhanh | Khung 3 |
| admin | cấu hình agent/model, phiên bản prompt, kiểm tra kết nối, chạy thử, rule set, rebuild chỉ mục, trạng thái chỉ mục, tìm kiếm tài liệu (cho evaluation) | Trang cấu hình, scripts |
| sync | `GET /sync?since=<event_id>` trả các sự kiện mới cho người gọi (theo quyền) | UI làm mới định kỳ |

Kiểm tra quyền ở tầng dịch vụ (SEC-3), dựa trên `PermissionService` (quyền hiện hành theo thời điểm).

### 5.2 Ngân sách ngữ cảnh với `NUM_CTX = 16384`

| Khối | Ngân sách (token) | Khi vượt |
|---|---|---|
| System prompt + [AN-TOÀN] + rule set rút gọn | ≤ 2.500 | Lỗi cấu hình: chặn lưu phiên bản prompt vượt ngân sách |
| Hồ sơ ca + tóm tắt | ≤ 800 | AG-5 tóm tắt lại ngắn hơn |
| Lịch sử gần nhất | ≤ 4.000 | Bỏ tin cũ nhất (đã nằm trong tóm tắt) |
| Tài liệu (RAG) | ≤ 5.000 | Giảm số khối, ưu tiên khối hạng cao |
| Câu hỏi hiện tại | ≤ 500 | Cắt và cảnh báo |
| Dự trữ đầu ra | 2.000 | — |
| Biên an toàn | ≥ 1.500 | — |

**Ước lượng token:** số ký tự / 2,5 cho tiếng Việt (bảo thủ). Hệ số được hiệu chỉnh từ `prompt_eval_count` thực tế, ghi trong `AiRun`.

**Lưu ý:** `NUM_CTX` 16k làm tăng bộ nhớ KV cache trên Mac mini. **Phải đo ở P0** xem RAM có đủ để giữ đồng thời qwen3:14b (16k) và bge-m3 mà không phải nạp lại model.

### 5.3 Hàng đợi LLM và năng lực

| Ưu tiên | Loại gọi | Ghi chú |
|---|---|---|
| 0 | Quy tắc cấp cứu (không dùng LLM) | Từ khoá trong rule set, chạy tức thì trước mọi thứ |
| 1 | AG-0 phân loại | Hết thời gian thì dùng mặc định an toàn (C2, không cho AI trả lời) |
| 2 | AG-1 (chế độ AI), AG-6 (kiểm tra trước khi gửi) | Người đang chờ phản hồi trực tiếp |
| 3 | Copilot AG-2..4 | Sinh nền, có thể huỷ nếu khách gửi tin mới (gợi ý cũ bị thay) |
| 4 | AG-7 quản lý | |
| 5 | AG-5 tóm tắt/hồ sơ ca | Gộp nhiều tin; tạm hoãn khi hàng đợi dài |

- **Giới hạn song song** khớp với `OLLAMA_NUM_PARALLEL` trên Mac mini, mặc định 2, tinh chỉnh sau khi đo.
- **Embedding** (bge-m3) dùng hàng riêng, vì nhanh và nhỏ.
- **Suy giảm có kiểm soát:** hàng đợi copilot dài quá N giây thì khung 2 hiện "gợi ý tạm chậm" và người trực vẫn tự trả lời được. Ollama mất kết nối thì:
  - chế độ AI tắt, mời chuyển người trực;
  - copilot tắt;
  - phân loại chỉ dùng quy tắc với mặc định an toàn;
  - tìm tài liệu chạy bằng BM25.

### 5.4 Triage (AG-0) = quy tắc + LLM

1. **Quy tắc** từ rule set đã duyệt:
   - từ khoá/mẫu T3-Khẩn thì `emergency` ngay;
   - hồ sơ ca > 75 tuổi / nhiều bệnh nền thì tối thiểu C3;
   - mang thai, trẻ < 3 tháng thì loại khỏi T2.
2. **LLM AG-0**, đầu ra có cấu trúc, cho phần còn lại.
3. **Lấy mức cao hơn** giữa quy tắc và LLM. Không bao giờ hạ tầng (BR-08b).

Khi rule set **chưa được duyệt** (feature flag tắt), chỉ áp dụng quy tắc cấp cứu tối thiểu theo khối [AN-TOÀN] và mặc định an toàn.

### 5.5 Đầu ra có cấu trúc với Ollama
- Dùng tham số `format` với JSON schema của từng agent. Kiểm tra bằng pydantic; sai thì thử lại 1 lần với thông báo lỗi; vẫn sai thì trả văn bản thô, gắn cảnh báo, ghi `AiRun.error`.
- Copilot cần **vừa stream vừa có cấu trúc**. Thứ tự trường trong lược đồ đặt `reply_draft` trước để UI hiện dần; phần còn lại hiện khi xong. Nếu stream JSON không ổn định với qwen3, phương án dự phòng là hai lượt: lượt 1 stream `reply_draft`, lượt 2 trả các trường còn lại (tốn thêm một lượt gọi). Chọn phương án sau khi đo ở P1.

### 5.6 Cập nhật thời gian thực cho Streamlit
- Streamlit không nhận WebSocket tiện, nên dùng `st.fragment(run_every=2s)` gọi `/sync?since=…` cho hàng chờ, tin mới, bảng trạng thái.
- Câu trả lời AI và gợi ý dùng **SSE stream** đọc trực tiếp trong lúc render (`st.write_stream`).
- Backend vẫn cung cấp WebSocket cho web app sau này.

### 5.7 Định danh người dùng khung 1 trên Streamlit
- Streamlit không có localStorage sẵn. Giai đoạn đầu dùng **mã cuộc chat** dạng ngắn, hiển thị cho người dùng để tiếp tục cuộc chat; token ẩn danh nằm trong `st.session_state`. Mất phiên trình duyệt thì nhập lại mã.
- Nhân sự đăng nhập bằng tài khoản/mật khẩu do backend quản lý; JWT nằm trong session. Nếu đơn vị có IdP thì cân nhắc `st.login` (OIDC).
- Đây là giới hạn đã biết của Streamlit, được giải quyết triệt để khi chuyển web app.

## 6. Lộ trình triển khai

| Giai đoạn | Công việc | Kết quả / điều kiện qua giai đoạn |
|---|---|---|
| **P0 · Nền & đo năng lực** | `git init`, `.gitignore` (`.env`, `qdrant_db/`, `storage/`, `data/`, cache); ghim phiên bản (`requirements.lock`); khung `pytest` + test cho `pdf_parser`, `lexical`, `rag` (chạy offline bằng BM25); script đo Ollama: độ trễ và thông lượng qwen3:14b ở 8k/16k, song song 1/2/4, RAM khi giữ cả bge-m3; embed collection mới đang chờ (`duoc_2018_v2`) | Repo có lịch sử; test xanh; **bảng số đo năng lực** → chốt NFR-1/2/4 và giới hạn song song. Cần Tailscale/Ollama hoạt động. |
| **P1 · Backend lõi + chế độ AI** | Khung FastAPI (R1, R2); storage repositories local + bộ test hợp đồng; ConfigService + AgentRegistry + phiên bản prompt; LLMGateway (nhiều lượt, đầu ra có cấu trúc, stream, hàng đợi); ContextBuilder; IndexManager (xanh–lục) + API admin ingest; Triage (quy tắc tối thiểu + AG-0); AG-1; UI khung 1 chế độ AI qua API; trang cấu hình model (bản đầu); chuyển `evaluation/` sang API | Khung 1 chế độ AI chạy end-to-end qua backend; `app.py` cũ ngưng dùng; AC-1.1–1.4, AC-4.1–4.5 |
| **P2 · Người trực** | Auth nhân sự; PermissionService; ConversationService (hàng chờ, tiếp nhận có khoá, chỉ định, chuyển, đẩy cấp, đóng/mở lại, SLA worker); CaseMemory (AG-5); Copilot AG-2..4; Guard (quy tắc + AG-6, chặn cứng thuốc kê đơn); UI khung 2; chuyển AI → người trực | AC-1.5–1.6, AC-2.x; vận hành thử nội bộ |
| **P3 · Quản lý** | MetricsService (tính từ sự kiện); AG-7 + công cụ đọc + đề xuất/xác nhận; form F-1..F-5; UI khung 3 + popup điều chỉnh nhanh; trang phân quyền (chứng chỉ, hiệu lực, lịch sử); audit log | AC-3.x, AC-4.6 |
| **P4 · An toàn & thí điểm** | Nạp rule set phân tầng + danh sách OTC **khi Hội đồng đã duyệt** (feature flag); bộ kiểm thử AC-5.1–5.3; thử tải theo số đo P0; thí điểm nhóm nhỏ; chỉnh prompt | Đủ điều kiện vận hành |
| **P5 · Mở rộng** | Repository PostgreSQL + công cụ chuyển dữ liệu; web app + WebSocket; đăng nhập người dùng (OTP); nếu tải tăng thì xem lại Q-A (Qdrant server) và Q-D (thêm máy GPU) | Theo nhu cầu |

**Tiến độ P0 (18/11/2026):**

| Việc | Trạng thái |
|---|---|
| git, `.gitignore`, push lên GitHub | Xong |
| Ghim phiên bản: `requirements.lock` (65 gói, lấy từ `.venv` đã kiểm thử), `requirements-dev.txt` | Xong |
| pytest: 31 test (parser, BM25, truy xuất, ngữ cảnh, ingest, lọc `<think>`, hồi quy trên Dược thư) | Xong, 31/31 qua |
| Sửa lỗi parser do test phát hiện: tiêu đề mục ở đầu trang bị coi nhầm là tên chạy đầu trang → **511 mục** bị gộp vào mục trước. Đã sửa (9.389 → 9.900 cặp chủ đề–mục; 16.160 chunk) | Xong |
| Script đo năng lực Ollama `scripts/bench_ollama.py` | Đã viết, **chưa chạy**: Mac mini offline từ ~07/11 |
| Embed collection `duoc_2018_v2` | **Chưa làm**: cần Ollama |

**Tiến độ P1 (18/11/2026):**

| Việc | Trạng thái |
|---|---|
| Backend FastAPI 1 worker, kiểm tra khoá Qdrant lúc khởi động (R1, R2) | Xong: backend thứ hai bị chặn kèm thông báo rõ |
| Repository local theo ngày giờ VN + bộ test hợp đồng (REPO-1/2, AC-4.3) | Xong |
| ConfigService + AgentRegistry + prompt có phiên bản, giới hạn ngân sách prompt (X-5, AC-4.1/4.2) | Xong |
| LLMGateway: nhiều lượt, đầu ra có cấu trúc, stream, model dự phòng, hàng đợi ưu tiên, **ngắt mạch** khi Ollama mất kết nối (X-4, X-7) | Xong |
| ContextBuilder theo ngân sách token (X-6) | Xong (hệ số 2,5 ký tự/token chờ hiệu chỉnh bằng số đo P0) |
| IndexManager: rebuild xanh–lục, quay lại, huỷ; **khoá Qdrant** (X-1, X-3, X-11) | Xong |
| Triage: quy tắc cấp cứu tối thiểu + AG-0, mặc định an toàn; AG-1; ChatService; API khung 1 + quản trị | Xong |
| UI Streamlit: khung 1 (đồng ý, chế độ AI, thẻ cấp cứu, chuyển người trực, mở lại bằng mã) + trang cấu hình model | Xong, kiểm tra bằng AppTest trên backend thật |
| `evaluation` chạy qua API (`--api`) | Xong |
| AC-1.1–1.4, AC-4.1–4.5 | Có test tự động (72 test). **AC-1.2 mới kiểm với LLM giả lập**, chưa với Ollama thật |
| Bỏ `app.py` cũ | Chưa: chờ chạy được với Ollama thật để đối chiếu |

**Tiến độ P2 (18/11/2026):**

| Việc | Trạng thái |
|---|---|
| Đăng nhập nhân sự (scrypt, token HMAC, khoá tạm sau 5 lần sai – SEC-1) | Xong |
| PermissionService: C1/C2/C3 lũy tiến, C2/C3 cần chứng chỉ đã xác minh + còn hạn, C3 phải là bác sĩ, tự hạ khi hết hạn; quyền thao tác; lịch sử chỉ thêm (AC-4.6) | Xong |
| OperatorService: hàng chờ lọc theo cấp, tiếp nhận có khoá, chỉ định (override + lý do), chuyển cần chấp nhận, đẩy cấp, đóng, mở lại ≤ 24 h / tạo cuộc chat liên kết, SLA, rời ca | Xong |
| Copilot AG-2/3/4 theo cấp (đầu ra có cấu trúc, nguồn chỉ nội bộ), AG-5 hồ sơ ca + tóm tắt (trường người trực sửa không bị ghi đè), AG-6 + quy tắc (thuốc kê đơn chặn cứng mọi cấp) | Xong. Gợi ý **chưa stream** (sinh nền, UI làm mới 3 giây) |
| `mutate()`: cập nhật cuộc chat an toàn khi AG-5 chạy nền song song | Xong |
| UI khung 2 + cập nhật khung 1 (chế độ người trực, tên/chức danh, tự làm mới) | Xong, kiểm tra bằng AppTest trên backend thật |
| `scripts/staff.py` tạo/cấp quyền nhân sự qua API | Xong |
| AC-1.5, 1.6, 2.1–2.9 | Có test tự động (tổng 105 test), **LLM giả lập** |
| Chưa làm (chuyển sang P3/P4): AI trả lời trong lúc chờ (Q-4), trạng thái `abandoned`, khảo sát cuối cuộc chat (UI-1.8), vị trí hàng chờ/thời gian ước tính (UI-1.5), âm báo (UI-2.10), danh mục thuốc kê đơn chính thức (Q-2 – file đang trống) | Ghi nhận |

**Tiến độ P3 (18/11/2026):**

| Việc | Trạng thái |
|---|---|
| MetricsService: chỉ số đặc tả 01 mục 4 tính từ sự kiện (BR-11); test đối chiếu số tính tay | Xong. Sửa định nghĩa "phản hồi TB" chỉ tính tin khách sau khi được giao |
| Form F-1…F-5 dựng bằng **code**; AG-7 chỉ viết phần nhận định (ghi rõ "AI – cần thẩm định") | Xong |
| Gọi công cụ trong LLMGateway (Ollama `tools`, OpenAI, giả lập) | Xong |
| AG-7: 9 công cụ đọc + 2 công cụ đề xuất; hỏi lại khi trùng tên; đề xuất kiểm tra hợp lệ ngay (AC-3.3); xác nhận/huỷ (D-6) | Xong |
| Báo cáo nhanh không cần LLM (UI-3.4), phiên quản lý được lưu, tải form Markdown (UI-3.5) | Xong. Xuất PDF để P5 |
| Bảng trạng thái (UI-3.3), xem cuộc chat chỉ đọc có nhật ký (UI-3.6, SEC-6) | Xong |
| Popup điều chỉnh nhanh (người trực / chỉ định / agent, bắt buộc lý do) | Xong; API có test, **giao diện popup chưa kiểm bằng AppTest** |
| Trang phân quyền: chứng chỉ + xác minh, cấp/quyền có hiệu lực từ–đến, mẫu quyền, lịch sử, cảnh báo hết hạn / vượt quyền | Xong |
| AC-3.1–3.6, AC-4.6 | Có test tự động (tổng 123 test), **AG-7 giả lập theo kịch bản** |

**Kết quả P0 với Ollama thật (18/11/2026):**

*Truy xuất* (`evaluation/run_eval.py --api`, 167 câu; page@1 = đúng thuốc ở vị trí đầu, section@1 = đúng cả mục):

| Phương án | page@1 | section@1 | Câu viết tay page@1 |
|---|---|---|---|
| Hệ thống cũ (chunk theo trang, chỉ vector) | 0,689 | 0,228 | 0,750 |
| Mới – chỉ vector | 0,802 | 0,413 | 0,900 |
| Mới – vector + BM25 trọng số ngang (bản đầu) | 0,731 | 0,383 | 0,650 |
| **Mới – BM25 chỉ cho câu không dấu (đang dùng)** | **0,796** | **0,503** | **0,900** |

*Năng lực Mac mini* (qwen3:14b, Ollama 0.40, [báo cáo đo](../benchmarks/ollama-20261118-2035.md)):

| Chỉ số | Đo được |
|---|---|
| Đọc prompt | ~100–117 token/giây |
| Sinh câu trả lời | ~9–10,7 token/giây |
| Xử lý song song | **Tuần tự** (1 yêu cầu một lúc) → `llm_max_parallel = 1` |
| RAM | qwen3 16k 11,2 GB + bge-m3 0,7 GB, nằm cùng lúc được |
| Embedding | 0,06 s/truy vấn (0,38 s khi đang sinh) |
| Ký tự/token (nội dung tài liệu) | ~3,2 → ước lượng dùng 2,8 |

*Thời gian thực tế từng tác vụ (lần chạy thử 3 khung):* phân loại AG-0 12–15 s; AI trả lời (chế độ AI) chữ đầu ~38 s, xong ~43 s; copilot ~115 s; kiểm tra trước khi gửi AG-6 ~10 s; AG-7 37–94 s.

*Kết luận – đề xuất chốt lại NFR (cần xác nhận):*

| NFR | Mục tiêu cũ | Thực tế với qwen3:14b / 1 Mac mini | Đề xuất |
|---|---|---|---|
| NFR-2 phân loại | ≤ 3 s | 12–15 s | ≤ 20 s (quy tắc cấp cứu vẫn tức thì) |
| NFR-1 gợi ý copilot | ≤ 15 s | ~115 s | ≤ 2 phút, sinh nền, người trực không phải chờ |
| AI trả lời (chữ đầu tiên) | — | ~38 s | ≤ 45 s |
| NFR-4 người trực đồng thời | 20 | Ollama tuần tự: mỗi tin khách ở chế độ người trực tốn ~2–3 phút GPU (AG-5 + copilot + AG-6) | **~3–5 người trực** thực tế; 20 người cần máy GPU mạnh hơn hoặc model nhỏ hơn cho AG-0/5/6 (xem lại Q-D) |

Đã áp dụng theo số đo: thời gian chờ từng agent, `llm_max_parallel = 1`, AG-5 ở chế độ AI chỉ chạy khi chuyển người trực, nhắc AG-7 không chép số liệu sau khi thẻ form đã hiển thị.

**Phụ thuộc chặn tiến độ:**
- **Ollama/Tailscale** chặn P0 (đo năng lực, embed) và mọi kiểm thử end-to-end.
- **Hội đồng duyệt `phan-tang.md`** chặn bật rule set ở P4. P1–P3 vẫn chạy được với quy tắc an toàn tối thiểu.

## 7. Chiến lược kiểm thử

| Loại | Phạm vi | Chạy khi |
|---|---|---|
| Unit | parser, BM25, rules, ContextBuilder (ngân sách), Guard quy tắc, Metrics, Permission (hiệu lực theo thời gian), chia ngày theo giờ VN | Mỗi lần commit |
| Hợp đồng repository | Cùng bộ test cho local (và DB sau này) – REPO-2 | Mỗi lần commit |
| API / tích hợp | Luồng tiếp nhận đồng thời (AC-2.2), chuyển/đẩy cấp, đề xuất–xác nhận (AC-3.3); LLM được **giả lập** bằng adapter trả kết quả cố định | Mỗi lần commit |
| Agent eval | Bộ câu hỏi gán nhãn cho AG-0, copilot, AG-6 (AC-5.x); chạy với Ollama thật | Khi đổi prompt/model/rule set; trước khi kích hoạt phiên bản prompt |
| RAG eval | `evaluation/run_eval.py` qua API | Khi rebuild chỉ mục |
| Tải | Mô phỏng N người trực / M cuộc chat theo số đo P0 | P4 |

## 8. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Ollama một máy không đủ năng lực (Q-D) | **Cao** | Đo ở P0; hàng đợi ưu tiên; suy giảm có kiểm soát; giới hạn số người trực đồng thời theo số đo; xem lại Q-D ở P5 |
| Mac mini / Tailscale mất kết nối | **Cao** | Chế độ suy giảm (5.3); cảnh báo trên bảng trạng thái quản lý; giám sát kết nối định kỳ |
| Backend là điểm lỗi đơn (Q-A) | Trung bình | Chạy dưới trình giám sát (launchd/systemd) tự khởi động lại; dữ liệu ghi bền trước khi phản hồi (NFR-5); khởi động nhanh (nạp Qdrant + BM25 vài giây) |
| qwen3:14b trả JSON sai lược đồ / stream JSON không ổn định | Trung bình | Kiểm tra + thử lại; phương án hai lượt (5.5); theo dõi tỉ lệ lỗi trong `AiRun` |
| Streamlit giới hạn (định danh người dùng, cập nhật thời gian thực) | Trung bình | Backend độc lập UI; mã cuộc chat; chuyển web app ở P5 |
| Rule set/danh mục chưa được duyệt | Trung bình | Feature flag; P1–P3 không phụ thuộc; mặc định an toàn |
| Tái cấu trúc làm hỏng RAG hiện có | Thấp sau P0 | git + test RAG; đánh giá RAG trước/sau |

## 9. Cập nhật kéo theo trong đặc tả

Các mục đặc tả đã/ sẽ được chỉnh cho khớp với plan:

| File | Nội dung | Trạng thái |
|---|---|---|
| README | D-1 (FastAPI + Streamlit), D-2 (Qdrant embedded, 1 tiến trình) | Đã cập nhật |
| 05 | Sơ đồ kiến trúc và mục "Lưu ý D-2" (đang ghi Qdrant server) → thay bằng mục 2–3 của plan này; NFR-1/2/4 ghi "tạm, chốt sau P0" | Cần cập nhật khi bắt đầu P1 |
| 02 | Trang cấu hình model: provider cloud mặc định **tắt** (dữ liệu nội bộ) | Cần cập nhật |
| 04 | Khoá file liên tiến trình (3.1) không còn cần, vì một tiến trình ghi | Cần cập nhật |
| 06 | Lộ trình 0–5 ánh xạ sang P0–P5 của plan này | Cần cập nhật |
