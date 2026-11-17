# 07 · Báo cáo xung đột với kiến trúc hiện tại

Ngày: 17/11/2026 · Mục đích: liệt kê các điểm đặc tả chat 3 khung (file 01–06) **xung đột** với code đang chạy, **trước khi** lập technical plan và đề xuất thay đổi.

Mỗi xung đột có bằng chứng trong code. Các phương án nêu ra chỉ để quyết định, chưa phải đề xuất cuối cùng.

## Hiện trạng kiến trúc (đã kiểm tra trong code)

| Thành phần | Hiện trạng | Vị trí |
|---|---|---|
| Giao diện | Một script Streamlit 1.66, một trang. Lịch sử chat nằm trong `st.session_state`, mất khi tải lại trang. Không có đăng nhập. | `app.py` |
| Vector DB | Qdrant **embedded** (`QdrantClient(path=...)`); một client dùng chung, đóng/tạm dừng khi ingest | `rag/rag.py` (`get_vector_store`, `close_vector_store(pause=True)`) |
| Ingest | Chạy từ nút trong app bằng tiến trình con; `--reset` **xoá collection rồi tạo lại** | `app.py` (`run_ingest`), `rag/ingest.py` |
| LLM | Hàm nhận `(question, context)`: **một lượt**, **một system prompt toàn cục** nạp lúc import, nhiệt độ/token/model toàn cục; không có đầu ra có cấu trúc, không gọi công cụ | `provider/llm.py`, `provider/prompts.py` |
| Cấu hình | Hằng số đọc từ `.env` lúc import và được import theo giá trị (`from config import X`) | `config.py` |
| Embedding + sinh văn bản | Ollama trên **một** Mac mini qua Tailscale (bge-m3 + qwen3:14b), `NUM_CTX = 8192` | `config.py`, `rag/embeddings.py` |
| Lưu trữ hội thoại | Không có | — |
| Kiểm thử / quản lý mã | Chỉ có script kiểm tra thủ công `test_check/`; thư mục **không phải git repo** | — |

## Danh sách xung đột

| Mã | Mức | Xung đột | Bằng chứng | Cần quyết định? |
|---|---|---|---|---|
| X-1 | **Chặn** | Qdrant embedded chỉ cho **một tiến trình** truy cập. Đặc tả cần: nhiều khung, nhiều người dùng; ingest, đánh giá, báo cáo chạy song song. | `_LOCK_MARKER = 'already accessed by another instance'`; app phải `close_vector_store(pause=True)` mỗi lần ingest | **Có (Q-A)** |
| X-2 | **Chặn** | Streamlit hiện là app một trang, trạng thái theo từng phiên trình duyệt. Đặc tả cần: trạng thái **dùng chung** giữa người dùng / người trực / quản lý (hàng chờ, tiếp nhận có khoá), cập nhật gần thời gian thực, đăng nhập theo vai trò. | `st.session_state.messages`; không có lớp dịch vụ; toàn bộ logic nằm trong script giao diện | **Có (Q-B)** |
| X-3 | **Cao** | Rebuild chỉ mục `--reset` **xoá collection đang phục vụ**. Khi có người dùng thật, mọi khung mất RAG trong suốt quá trình ingest (hàng chục phút). | `create_collection`: `client.delete_collection(COLLECTION_NAME)` trước khi tạo lại | **Có (Q-C)** |
| X-4 | **Cao** | Tầng LLM chỉ hỗ trợ một lượt `(question, context)` với một prompt toàn cục. Đặc tả cần: prompt/model/nhiệt độ **theo từng agent**, **nhiều lượt** (lịch sử chat), **đầu ra có cấu trúc** (AG-0, AG-2..6), **gọi công cụ** (AG-7), đổi prompt/model **lúc đang chạy**. | `call_*_api(question, context, model)`; `SYSTEM_PROMPT = _load_system_prompt()` ở cấp module | Không: bắt buộc tái cấu trúc; chỉ cần biết trước phạm vi |
| X-5 | **Cao** | Cấu hình được import theo giá trị lúc khởi động, nên trang cấu hình model không thể đổi model/prompt mà không khởi động lại. | `from config import GENERATION_MODEL, ...` ở nhiều module | Không: bắt buộc thêm lớp cấu hình động |
| X-6 | **Cao** | **Ngân sách ngữ cảnh** của copilot vượt `NUM_CTX = 8192`: system prompt + [AN-TOÀN] (~1,5k token) + lịch sử 6.000 ký tự (~2k) + tài liệu 9.000 ký tự (~3k) + hồ sơ/tóm tắt (~0,5k) + đầu ra JSON (~1–1,5k) ≈ 8–8,5k token. Ollama sẽ **cắt ngữ cảnh im lặng**. | `NUM_CTX = 8192`, `MAX_CONTEXT_CHARS = 9000`; đặc tả 03 mục 1.3 | **Có (Q-D)** |
| X-7 | **Cao** | **Năng lực Ollama:** một Mac mini phục vụ embedding + AG-0 + AG-5 + copilot + AG-6 + AG-7 cho tối đa 20 người trực (NFR-4). Mỗi tin của khách sinh ~4 lượt gọi LLM; Ollama xử lý song song hạn chế và phải nạp/thay model (bge-m3, qwen3:14b, model phân loại). NFR-1/NFR-2 (≤ 3s phân loại, ≤ 15s gợi ý) khó đạt. Hiện máy còn **mất kết nối** (Tailscale tắt). | `config.py`; kết quả kiểm tra kết nối trong các phiên trước | **Có (Q-D)** |
| X-8 | Trung bình | Lưu trữ file local dùng khoá trong tiến trình. Chạy nhiều tiến trình (vd ingest/đánh giá/báo cáo, hay nhiều worker Streamlit) cần khoá file liên tiến trình. | Đặc tả 04 mục 3.1 | Phụ thuộc Q-B |
| X-9 | Trung bình | Truy xuất hiện ghép **câu hỏi trước** khi câu ngắn; đặc tả muốn truy vấn RAG dùng **hồ sơ ca + tóm tắt**. `MIN_SCORE` trả về rỗng sẽ làm copilot mất ngữ cảnh ở câu hỏi lan man. | `rag/rag.py` `_with_history`, `MIN_SCORE` | Không: mở rộng tham số `retrieve()` |
| X-11 | **Cao** (phát hiện ở P1) | Qdrant embedded **không an toàn khi nhiều luồng** ghi/đọc đồng thời. Đã đo: lỗi SQLite "API misuse" và **mất điểm im lặng** (189 điểm trong bộ nhớ, còn 177 trên đĩa). Backend FastAPI chạy request trên nhiều luồng, rebuild chạy song song. | Thử nghiệm 8 luồng, 400 thao tác | Không: đã xử lý – mọi lời gọi client đi qua một khoá (`LockedClient`); đo lại 200/200, chờ tối đa 6 ms |
| X-10 | Quy trình | Không có git, không có test tự động, phụ thuộc không ghim phiên bản (`>=`). Tái cấu trúc lớn (X-2, X-4, X-5) mà không có quản lý phiên bản và test là rủi ro cao. | `git status`: not a git repository; `requirements.txt` | **Có (Q-E)** |

## Câu hỏi cần quyết định trước khi lập technical plan

| Mã | Câu hỏi | Các phương án |
|---|---|---|
| Q-A | Qdrant | (1) Chuyển sang **Qdrant server** bằng Docker (máy đã có Docker 29.8). (2) Giữ embedded, mọi truy cập Qdrant đi qua **một tiến trình backend duy nhất**; ingest chạy trong tiến trình đó. |
| Q-B | Kiến trúc ứng dụng | (1) **Streamlit nhiều trang + lớp dịch vụ trong cùng tiến trình** (trạng thái dùng chung qua repository, làm mới định kỳ bằng `st.fragment`). (2) **Backend FastAPI** (API + WebSocket) + Streamlit làm client. (3) Backend FastAPI + **web app riêng** ngay từ đầu. |
| Q-C | Rebuild chỉ mục khi đang phục vụ | (1) **Xanh–lục (blue-green):** dựng collection mới song song rồi chuyển alias (cần Qdrant server). (2) Rebuild chỉ chạy trong **giờ bảo trì**, chặn khung 1/2 trong lúc đó. |
| Q-D | Hạ tầng LLM cho nhiều agent | (1) Giữ Ollama Mac mini, **tăng `NUM_CTX`** lên 16k và giảm ngân sách lịch sử/tài liệu; AG-0 dùng quy tắc + model nhỏ. (2) Thêm **máy Ollama/GPU** thứ hai cho sinh văn bản, Mac mini chỉ embedding. (3) Cho phép **provider cloud** (Gemini/OpenAI) cho agent không xử lý dữ liệu khách, hoặc cho tất cả (liên quan Q-5 về dữ liệu ra ngoài). |
| Q-E | Quy trình | Khởi tạo **git repo** và bộ test tự động (pytest) trước khi tái cấu trúc? |

## Quyết định (17/11/2026)

| Mã | Quyết định | Hệ quả |
|---|---|---|
| Q-A | **Giữ Qdrant embedded**, mọi truy cập qua **một tiến trình** | Backend là tiến trình duy nhất mở Qdrant (1 worker). Ingest, đánh giá, tra cứu tài liệu đều đi qua backend. |
| Q-B | **Backend FastAPI + Streamlit làm client** | Streamlit không còn import `rag`/`provider`, chỉ gọi API. |
| Q-C | Suy ra từ Q-A | Rebuild **xanh–lục ở mức ứng dụng**: dựng collection mới song song trong cùng client embedded, xong thì chuyển con trỏ "collection đang dùng". Không cần giờ bảo trì. |
| Q-D | **Giữ Ollama, `NUM_CTX` 16k**, giảm ngân sách ngữ cảnh | Dữ liệu ở nội bộ. Năng lực phục vụ là **rủi ro lớn nhất**: NFR-1/2/4 chỉ là mục tiêu tạm, phải đo trên Mac mini thật trước khi chốt. |
| Q-E | **git + pytest trước** khi tái cấu trúc | Giai đoạn P0 của technical plan. |

Chi tiết thay đổi: [08-technical-plan.md](08-technical-plan.md).
