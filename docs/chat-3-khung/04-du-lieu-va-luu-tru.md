# 04 · Dữ liệu và lưu trữ

## 1. Nguyên tắc

- **Giai đoạn 1:** lưu file local. Mọi đọc/ghi đi qua **lớp repository** có giao diện cố định. Sau này chuyển sang DB (PostgreSQL khuyến nghị) chỉ cần viết bản cài đặt repository mới và đổi cấu hình `STORAGE_BACKEND=local|postgres`. Tầng nghiệp vụ và giao diện không đổi.
- **Định danh:** dùng ID sắp xếp được theo thời gian (ULID hoặc UUIDv7) cho mọi thực thể. ID này dùng nguyên được làm khoá chính trong DB.
- **Thời gian:** mọi mốc lưu dạng ISO 8601 UTC, ví dụ `2026-11-17T08:15:30.123Z`. "Ngày" để chia file và báo cáo tính theo **Asia/Ho_Chi_Minh** (D-5).
- **Bất biến:**
  - tin nhắn và sự kiện **chỉ thêm, không sửa**; sửa/thu hồi một tin là một sự kiện mới;
  - các thực thể có trạng thái (cuộc chat, nhân sự…) được sửa, nhưng mỗi thay đổi sinh một sự kiện nhật ký.
- **Phiên bản lược đồ:** mỗi bản ghi có `schema_version`, để viết công cụ chuyển đổi khi lược đồ thay đổi.

## 2. Thực thể

### 2.1 Danh sách

| Thực thể | Mô tả | Thay đổi |
|---|---|---|
| `EndUser` | Người dùng khung 1 | Sửa được |
| `Staff` | Nhân sự: người trực, quản lý, quản trị | Sửa được |
| `Credential` | Chứng chỉ chuyên môn của nhân sự | Sửa được |
| `PermissionGrant` | Một lần cấp/thu hồi quyền | Chỉ thêm |
| `Conversation` | Cuộc trò chuyện của người dùng | Sửa được (trạng thái) |
| `Message` | Tin nhắn trong cuộc trò chuyện | Chỉ thêm |
| `ConversationEvent` | Tiếp nhận, chỉ định, chuyển, đẩy cấp, đóng, mở lại… | Chỉ thêm |
| `CaseProfile` | Hồ sơ ca của cuộc trò chuyện | Sửa được, có lịch sử |
| `AiSuggestion` | Gợi ý copilot và cách người trực xử lý | Chỉ thêm (trạng thái xử lý cập nhật 1 lần) |
| `AiRun` | Mỗi lần gọi agent: agent, model, prompt version, token, thời gian, lỗi | Chỉ thêm |
| `GuardCheck` | Kết quả kiểm tra trước khi gửi (AG-6) | Chỉ thêm |
| `ManagerSession` / `ManagerMessage` | Phiên chat của quản lý với AG-7 | Phiên sửa được, tin chỉ thêm |
| `ActionProposal` | Thẻ đề xuất thao tác của AG-7 và kết quả xác nhận | Sửa 1 lần (xác nhận/huỷ) |
| `StaffPresence` | Lịch sử trạng thái trực | Chỉ thêm |
| `Feedback` | Đánh giá của khách | Chỉ thêm |
| `AgentConfig` / `PromptVersion` | Cấu hình agent và các phiên bản prompt | Phiên bản chỉ thêm |
| `Setting` | Cấu hình hệ thống (SLA, ngưỡng…) | Sửa được, có lịch sử |
| `AuditLog` | Nhật ký thao tác quản trị/quản lý | Chỉ thêm |

### 2.2 Trường chính

**Conversation**

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `id` | ULID | |
| `end_user_id` | ULID | |
| `mode` | `ai` / `human` | Chế độ hiện tại |
| `status` | `ai_active` / `waiting` / `assigned` / `closed` / `abandoned` | |
| `required_level` | `none` / `C1` / `C2` / `C3` | Theo AG-0 hoặc đẩy cấp |
| `urgency` | `normal` / `soon` / `emergency` | |
| `assignee_id` | ULID \| null | Người trực phụ trách hiện tại |
| `previous_conversation_id` | ULID \| null | Liên kết cuộc chat trước (BR-06) |
| `summary` | text | Do AG-5 cập nhật |
| `summary_upto_message_id` | ULID | Tóm tắt đã bao phủ tới tin nào |
| `created_at`, `updated_at`, `closed_at` | thời gian | |
| `days` | danh sách ngày `YYYY-MM-DD` | Các ngày có tin, để tìm theo ngày |
| `version` | số nguyên | Khoá lạc quan khi tiếp nhận/chỉ định (BR-01) |

**Message**

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `id` | ULID | |
| `conversation_id` | ULID | |
| `sender_type` | `end_user` / `ai` / `staff` / `system` | |
| `sender_id` | ULID \| null | Nhân sự hoặc người dùng |
| `content` | text | Nội dung hiển thị cho khách |
| `sources` | danh sách | Chỉ với tin AI ở chế độ AI |
| `suggestion_id` | ULID \| null | Gợi ý đã dùng để tạo tin (nếu có) |
| `send_mode` | `typed` / `ai_unedited` / `ai_edited` | Với tin của nhân sự |
| `ai_run_id` | ULID \| null | Với tin AI |
| `created_at` | thời gian | |
| `local_date` | `YYYY-MM-DD` | Ngày theo giờ Việt Nam |

**AiSuggestion**: `id`, `conversation_id`, `for_message_id` (tin khách), `staff_id`, `agent_id`, `prompt_version`, `model`, các trường lược đồ copilot (`reply_draft`, `follow_up_questions`, `internal_notes`, `sources`, `scope_check`, `red_flags`, `monitoring_advice`, `confidence`), `regenerate_instruction`, `outcome` (`sent_unedited` / `edited` / `discarded` / `superseded`), `final_message_id`, `edit_ratio`.

**ConversationEvent**: `id`, `conversation_id`, `type` (`created`, `mode_changed`, `queued`, `claimed`, `assigned`, `transfer_requested`, `transferred`, `escalated`, `closed`, `reopened`, `abandoned`, `profile_edited`), `actor_type`, `actor_id`, `data` (người nhận, cấp cũ/mới, lý do…), `created_at`, `local_date`.

**PermissionGrant**: `id`, `staff_id`, `kind` (`level` / `capability`), `key` (vd `level` hoặc `ai.send_unedited`), `value`, `effective_from`, `effective_to`, `reason`, `granted_by`, `source` (`settings_page` / `quick_popup` / `agent_proposal`), `proposal_id`, `created_at`. **Quyền hiện hành** = bản ghi mới nhất còn hiệu lực cho mỗi `key`.

## 3. Bố cục lưu trữ local (giai đoạn 1)

```
storage/                                 (STORAGE_DIR, mặc định ./storage)
├── meta.json                            schema_version, ngày tạo
├── users/
│   ├── end_users.jsonl                  bản ghi người dùng (chỉ thêm; bản mới nhất theo id là hiện hành)
│   └── staff.jsonl
├── permissions/
│   └── grants.jsonl
├── conversations/
│   └── <conversation_id>.json           trạng thái hiện tại của cuộc chat + hồ sơ ca
├── messages/
│   └── 2026/11/17/                      ← CHIA THEO NGÀY (giờ Việt Nam)
│       ├── <conversation_id>.jsonl      tin nhắn của cuộc chat trong ngày đó
│       └── _events.jsonl                mọi ConversationEvent trong ngày
├── ai/
│   └── 2026/11/17/
│       ├── suggestions.jsonl
│       ├── runs.jsonl
│       └── guard_checks.jsonl
├── manager/
│   ├── sessions/<session_id>.json
│   └── 2026/11/17/<session_id>.jsonl    tin trong phiên quản lý theo ngày
├── config/
│   ├── agents.json                      agent → model, tham số, phiên bản prompt đang dùng
│   ├── prompts/<agent_id>/v<N>.txt      các phiên bản prompt
│   └── settings.json
├── audit/
│   └── 2026/11/17.jsonl
└── indexes/                             chỉ mục dựng lại được (xem 3.2)
    ├── conversations_by_day.json
    └── conversations_by_user.json
```

### 3.1 Quy tắc ghi
- **Ghi nối thêm (append)** cho `.jsonl`: mỗi dòng một bản ghi JSON đầy đủ.
- **Ghi nguyên tử** cho file trạng thái `.json`: ghi ra file tạm rồi đổi tên, như cách `ingest_state.json` đang làm.
- **Khoá:**
  - trong một tiến trình: khoá theo `conversation_id`;
  - giữa nhiều tiến trình: khoá file;
  - tiếp nhận/chỉ định dùng khoá lạc quan theo trường `version`.
- Cuộc chat kéo dài qua nửa đêm thì tin sau 00:00 (giờ Việt Nam) được ghi vào thư mục ngày mới. Trường `days` của cuộc chat ghi lại cả hai ngày.

### 3.2 Chỉ mục
Chỉ mục trong `indexes/` chỉ để tăng tốc và **luôn dựng lại được** từ dữ liệu gốc. Có lệnh "dựng lại chỉ mục" để dùng khi file bị hỏng.

### 3.3 Sao lưu & lưu giữ
- Sao lưu hằng ngày thư mục `storage/` (nén theo ngày).
- Thời hạn lưu giữ cấu hình được, ví dụ 5 năm. Cần pháp chế xác nhận (Q-6). Dữ liệu quá hạn được lưu trữ ngoại tuyến hoặc xoá theo quy trình có nhật ký.

## 4. Lớp repository (giao diện để chuyển sang DB)

Mô tả theo chức năng; tên chỉ để minh hoạ, không phải code.

| Repository | Thao tác chính |
|---|---|
| `ConversationRepository` | tạo; lấy theo id; cập nhật trạng thái **có kiểm tra version**; tìm theo người dùng / người trực / ngày / trạng thái / cấp; danh sách hàng chờ |
| `MessageRepository` | thêm tin; lấy tin của cuộc chat (toàn bộ, N tin gần nhất, sau một id); lấy tin theo ngày |
| `EventRepository` | thêm sự kiện; lấy theo cuộc chat; lấy theo khoảng ngày (cho báo cáo) |
| `CaseProfileRepository` | lấy; cập nhật kèm nguồn (`ai` / `staff`) và lịch sử |
| `AiRepository` | thêm gợi ý, cập nhật kết quả xử lý gợi ý (một lần); thêm AiRun, GuardCheck; truy vấn theo người trực/khoảng ngày |
| `StaffRepository` | nhân sự, chứng chỉ, trạng thái trực |
| `PermissionRepository` | thêm grant; quyền hiện hành của một người; lịch sử |
| `ManagerRepository` | phiên, tin, đề xuất thao tác |
| `ConfigRepository` | cấu hình agent, phiên bản prompt, settings |
| `AuditRepository` | thêm và truy vấn nhật ký |

**Yêu cầu:**
- REPO-1: Tầng nghiệp vụ **không** đọc/ghi file trực tiếp.
- REPO-2: Có bộ kiểm thử dùng chung chạy được trên mọi bản cài đặt repository (local, DB), để đảm bảo hành vi giống nhau.
- REPO-3: Có công cụ **chuyển dữ liệu** từ local sang DB, đọc toàn bộ `storage/` và ghi qua repository DB; chạy lại nhiều lần vẫn cho cùng kết quả.
- REPO-4: Ánh xạ sang DB:
  - mỗi thực thể là một bảng;
  - `.jsonl` theo ngày thành bảng có cột `local_date` và chỉ mục (`conversation_id`, `created_at`);
  - có thể phân vùng bảng `messages` theo tháng.

## 5. Dữ liệu cá nhân

- Dữ liệu sức khoẻ trong cuộc chat là **dữ liệu cá nhân nhạy cảm**.
- Chỉ người phụ trách, quản lý và người được cấp `chat.view_all` được xem nội dung.
- Mọi lượt xem cuộc chat của người không phụ trách đều ghi `AuditLog`.
- Báo cáo và form của quản lý chỉ hiện định danh người dùng ở mức cần thiết. Có tuỳ chọn **ẩn danh hoá** khi xuất báo cáo.
- Gửi dữ liệu cuộc chat tới provider AI bên ngoài (Gemini, OpenAI) là chuyển dữ liệu ra ngoài. Cần ghi rõ trong thông báo đồng ý và cho phép cấu hình **chỉ dùng model nội bộ (Ollama)** cho agent xử lý dữ liệu khách (Q-5).
