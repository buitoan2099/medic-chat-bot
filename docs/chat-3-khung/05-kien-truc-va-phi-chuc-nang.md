# 05 · Kiến trúc và yêu cầu phi chức năng

## 1. Kiến trúc tổng thể

```
┌──────────── Giao diện ────────────┐
│ Khung 1 │ Khung 2 │ Khung 3 │ Cấu hình model │ Phân quyền │
└────┬─────────┬─────────┬──────────────┬───────────┘
     │   (giai đoạn 1: Streamlit nhiều trang, làm mới định kỳ;
     │    giai đoạn 2: web app + API + WebSocket)
┌────▼──────────────────────── Tầng dịch vụ ─────────────────────────┐
│ ConversationService   (tạo, chế độ, hàng chờ, tiếp nhận, chỉ định,  │
│                        chuyển, đẩy cấp, đóng/mở lại, SLA)           │
│ MessagingService      (gửi/nhận tin, thông báo)                     │
│ CopilotService        (gọi AG-2..4 theo cấp, tạo lại, lưu gợi ý)    │
│ GuardService          (quy tắc + AG-6)                              │
│ CaseMemoryService     (AG-5: hồ sơ ca, tóm tắt cập nhật dần)        │
│ TriageService         (AG-0)                                         │
│ ManagerAgentService   (AG-7 + công cụ + đề xuất thao tác)           │
│ MetricsService        (tính chỉ số từ sự kiện – BR-11)              │
│ PermissionService     (quyền hiện hành, hiệu lực, kiểm tra quyền)   │
│ AgentRegistry         (cấu hình agent, phiên bản prompt, model)     │
└────┬──────────────────────┬────────────────────────┬───────────────┘
     │                      │                        │
┌────▼──────────┐  ┌────────▼─────────────┐  ┌──────▼────────────────┐
│ Repository    │  │ RAG (code hiện có)   │  │ Provider LLM (hiện có) │
│ local / DB    │  │ rag.retrieve, BM25,  │  │ Ollama / Gemini /      │
│ (04)          │  │ Qdrant server (D-2)  │  │ OpenAI, streaming      │
└───────────────┘  └──────────────────────┘  └────────────────────────┘
```

## 2. Tích hợp với code hiện có

| Thành phần hiện có | Dùng lại thế nào |
|---|---|
| `rag/rag.py` (`retrieve`, `build_context_blocks`, `format_context`) | Cung cấp khối `TÀI LIỆU` cho AG-1 đến AG-4 và AG-7. Truy vấn RAG ghép câu hỏi với hồ sơ ca và chủ đề đang bàn, như cơ chế câu hỏi nối tiếp hiện có nhưng dùng tóm tắt thay vì chỉ câu trước. |
| `rag/lexical.py`, `rag/pdf_parser.py`, `rag/ingest.py` | Giữ nguyên |
| `provider/llm.py` (gọi thường + streaming 3 provider) | Mở rộng để nhận **cấu hình theo agent** (provider, model, nhiệt độ, token) thay vì cấu hình toàn cục; thêm chế độ đầu ra có cấu trúc và gọi công cụ cho AG-7. |
| `provider/prompts.py` (`SYSTEM_PROMPT_FILE`, `ThinkFilter`) | Thay thành `AgentRegistry` đọc prompt theo agent và phiên bản; giữ `ThinkFilter`. |
| `app.py` (Streamlit một trang) | Trở thành khung 1 chế độ AI; các khung còn lại là trang mới. |
| `config.py`, `.env` | Thêm `STORAGE_BACKEND`, `STORAGE_DIR`, `QDRANT_URL` (chế độ server), cấu hình SLA mặc định. Cấu hình agent chuyển vào `storage/config/agents.json` để sửa được trên giao diện. |

**Lưu ý D-2:**
- Qdrant local (`QdrantClient(path=…)`) chỉ cho một tiến trình truy cập. Hệ thống nhiều người dùng, cùng việc chạy ingest hay báo cáo song song, cần Qdrant **server**.
- Code chỉ cần đổi cách khởi tạo client theo `QDRANT_URL`. Các phần còn lại không đổi.

## 3. Cập nhật thời gian thực

| Giai đoạn | Cơ chế | Mục tiêu độ trễ |
|---|---|---|
| 1 (Streamlit) | Làm mới định kỳ theo vùng: hàng chờ và tin mới mỗi 2–3 giây; bảng trạng thái quản lý 10 giây | Tin mới hiển thị ≤ 5 giây |
| 2 (web app) | WebSocket/SSE đẩy sự kiện | ≤ 1 giây |

Sinh câu trả lời AI (chế độ AI, gợi ý copilot) luôn dùng **streaming**.

## 4. Yêu cầu phi chức năng

| Mã | Yêu cầu |
|---|---|
| NFR-1 | Gợi ý copilot bắt đầu hiển thị trong ≤ 5 giây (model cloud) hoặc ≤ 15 giây (Ollama 14B) sau khi tin khách đến. Gợi ý sinh nền, **không chặn** người trực gõ tin. |
| NFR-2 | AG-0 phân loại trong ≤ 3 giây. Quá thời gian thì coi như `required_level = C2`, `ai_allowed = false` (an toàn), và ghi lỗi. |
| NFR-3 | Model chính lỗi thì tự chuyển sang model dự phòng. Cả hai cùng lỗi thì khung 2 vẫn hoạt động, chỉ không có gợi ý (hiện thông báo). Khung 1 chế độ AI báo lỗi và mời chuyển sang người trực. |
| NFR-4 | Giai đoạn 1 chịu tải: 20 người trực và 200 cuộc chat đồng thời trên một máy chủ. |
| NFR-5 | Không mất tin nhắn: tin được ghi bền vững trước khi báo "đã gửi". |
| NFR-6 | Truy vết: mỗi tin AI/gợi ý tra ngược được agent, phiên bản prompt, model, đoạn tài liệu đã dùng. |
| NFR-7 | Giao diện khung 1 dùng được trên điện thoại. |

## 5. Bảo mật

| Mã | Yêu cầu |
|---|---|
| SEC-1 | Đăng nhập cho nhân sự (người trực, quản lý, quản trị). Mật khẩu băm (bcrypt/argon2); khoá tạm sau nhiều lần sai; khuyến nghị xác thực 2 lớp cho quản lý/quản trị. |
| SEC-2 | Người dùng khung 1 tối thiểu có định danh phiên (ẩn danh). Có tuỳ chọn đăng nhập (số điện thoại/OTP) để xem lại lịch sử trên nhiều thiết bị (Q-7). |
| SEC-3 | Kiểm tra quyền ở **tầng dịch vụ**, không chỉ ẩn nút trên giao diện. |
| SEC-4 | Khoá API của provider chỉ nằm trong `.env`/kho bí mật; không bao giờ hiển thị ra giao diện hay ghi vào log. |
| SEC-5 | Chống chèn lệnh (prompt injection): nội dung tài liệu và tin của khách luôn được đặt trong khối dữ liệu có nhãn. Prompt có khối [AN-TOÀN]. AG-7 chỉ dùng công cụ đọc + đề xuất (D-6). |
| SEC-6 | Ghi nhật ký mọi thao tác quản lý/quản trị và mọi lượt xem cuộc chat không thuộc mình. |

## 6. Tuân thủ và an toàn y tế

- **Thông báo và đồng ý** ở khung 1: kênh tham khảo, không thay thế khám chữa bệnh; dữ liệu được lưu và có thể được xử lý bởi AI (nêu rõ nếu dùng provider bên ngoài); cấp cứu gọi 115.
- **Không kê đơn trực tuyến.** Hệ thống chỉ tư vấn thông tin thuốc, tư vấn thuốc không kê đơn cho bệnh nhẹ, và hẹn khám trực tiếp với ca nặng. Tư vấn từ xa vẫn phải tuân thủ quy định về khám chữa bệnh từ xa. Danh mục và tiêu chí phân tầng trong [../phan-tang.md](../phan-tang.md) cần **pháp chế và hội đồng chuyên môn xác nhận** (Q-1).
- **Bảo vệ dữ liệu cá nhân:** dữ liệu sức khoẻ là dữ liệu nhạy cảm theo quy định về bảo vệ dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP). Cần đánh giá tác động xử lý dữ liệu và xác định nơi lưu trữ, thời hạn lưu (Q-5, Q-6).
- **Giới hạn tài liệu:** Dược thư 2018 có thể đã cũ. Prompt đã có câu cảnh báo, nhưng đơn vị cần kế hoạch cập nhật tài liệu.
- **Giám sát an toàn:** báo cáo hằng tuần các ca có `urgency = emergency`, các cảnh báo `block` mà người trực vẫn gửi, và các khiếu nại, để hội đồng chuyên môn xem lại.
