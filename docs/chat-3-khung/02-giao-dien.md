# 02 · Giao diện

Các mô tả bố cục dưới đây là khung chức năng, không phải thiết kế đồ hoạ cuối cùng.

## 1. Khung 1 – Người dùng

```
┌──────────────────────────────────────────────────────────┐
│ [Tên dịch vụ]                         [Cuộc chat mới]    │
├──────────────────────────────────────────────────────────┤
│ (Lần đầu) Thông báo & đồng ý  ─  [Tôi đồng ý]            │
│ Chọn chế độ:  ( ) Chat với AI    ( ) Chat với người trực │
│ Thông tin giúp tư vấn (tuỳ chọn): tuổi, giới, mang thai, │
│ dị ứng, bệnh nền                                          │
├──────────────────────────────────────────────────────────┤
│  Tin nhắn ...                                             │
│  [AI] ... (Tài liệu tham khảo ▸)   ← chỉ ở chế độ AI      │
│  [Hệ thống] Câu hỏi cần người trực → [Chat với người trực]│
│  [Người trực – Dược sĩ Lan] ...                           │
├──────────────────────────────────────────────────────────┤
│ Trạng thái: Đang chờ người trực (vị trí 3, ~4 phút)       │
│ [Nhập tin nhắn ......................]  [Gửi]            │
└──────────────────────────────────────────────────────────┘
```

| Mã | Yêu cầu |
|---|---|
| UI-1.1 | Màn hình đồng ý hiện ở lần đầu của mỗi thiết bị/tài khoản; lưu thời điểm đồng ý. |
| UI-1.2 | Chế độ AI: trả lời dạng streaming. Có nút "Chuyển sang người trực" cố định. |
| UI-1.3 | Agent từ chối vì là câu hỏi chẩn đoán/kê thuốc thì hiện thẻ hệ thống, có nút chuyển sang người trực bằng một chạm. |
| UI-1.4 | Phát hiện dấu hiệu cấp cứu thì hiện thẻ đỏ nổi bật: "Gọi 115 / đến cơ sở y tế gần nhất ngay", trước mọi nội dung khác. |
| UI-1.5 | Khi chờ: hiện vị trí trong hàng chờ và thời gian ước tính. Có thể tiếp tục hỏi AI trong lúc chờ (tuỳ chọn, xem Q-4). |
| UI-1.6 | Tin của người trực hiển thị tên hiển thị và chức danh (ví dụ "Dược sĩ", "Bác sĩ"); không hiện tên đầy đủ nếu chưa được cấu hình cho phép. |
| UI-1.7 | Có danh sách các cuộc chat trước của người dùng, nhóm theo ngày; mở lại để xem. |
| UI-1.8 | Cuối cuộc chat do người trực đóng: khảo sát 1–5 sao kèm nhận xét (tuỳ chọn). |
| UI-1.9 | Chế độ AI hiển thị nguồn tài liệu dạng thu gọn (mặc định, xem Q-3). Chế độ người trực không hiển thị nguồn. |

## 2. Khung 2 – Người trực ban

```
┌────────────────┬───────────────────────────────┬──────────────────────────┐
│ HÀNG CHỜ (4)   │ Cuộc chat #A12 · Nguyễn V. A   │ GỢI Ý AI (Agent C2)      │
│ ● #A12 C2 khẩn │ Hồ sơ ca: 34t, nữ, đang cho bú │ ┌──────────────────────┐ │
│   3' chờ       │ dị ứng: penicilin              │ │ Bản nháp gửi khách   │ │
│ ● #A15 C1 4'   │ ────────────────────────────── │ │ (sửa trực tiếp)      │ │
│ [Tiếp nhận]    │ [Khách] ... (lịch sử cả phần   │ └──────────────────────┘ │
│                │   chat AI trước đó)            │ ⚠ Vượt quyền: ...        │
│ CỦA TÔI (2/5)  │ [Tôi] ...                      │ ⚠ Dấu hiệu nặng: ...     │
│ ● #A09 mới tin │                                │ Ghi chú nội bộ ▸         │
│ ● #A07         │                                │ Nguồn tài liệu ▸ (tr.)   │
│                │ [Soạn tin ...............]     │ [Gửi luôn] [Dùng & sửa]  │
│ Trạng thái:    │ [Gửi] [Chuyển] [Đẩy cấp]       │ [Tạo lại: "..."] [Bỏ]    │
│ (●Online ▾)    │ [Đóng cuộc chat]               │                          │
└────────────────┴───────────────────────────────┴──────────────────────────┘
```

| Mã | Yêu cầu |
|---|---|
| UI-2.1 | Cột trái có hai mục. **Hàng chờ:** chỉ cuộc chat đủ cấp với người trực; sắp theo độ khẩn rồi thời gian chờ; hiện cấp cần thiết ước lượng. **Của tôi:** cuộc chat đang phụ trách, đánh dấu có tin mới. |
| UI-2.2 | Nút "Tiếp nhận": nếu người khác đã nhận trước thì báo "Cuộc chat đã được tiếp nhận". |
| UI-2.3 | Cột giữa: toàn bộ lịch sử cuộc chat, kể cả phần chat với AI (gắn nhãn "AI") và các sự kiện (chuyển, chỉ định…). Hồ sơ ca sửa được và có lịch sử thay đổi. |
| UI-2.4 | Cột phải: gợi ý tự sinh khi có tin mới của khách (streaming). Gồm bản nháp, các cảnh báo, ghi chú nội bộ, nguồn. Ghi chú nội bộ và nguồn không bao giờ được gửi cho khách. |
| UI-2.5 | "Gửi luôn" chỉ hiện với người có quyền `ai.send_unedited`. "Dùng & sửa" chép bản nháp vào ô soạn tin. |
| UI-2.6 | "Tạo lại" cho nhập chỉ dẫn ngắn; giữ lại các phiên bản gợi ý trước để xem lại. |
| UI-2.7 | Kiểm tra trước khi gửi (xem 01, mục 3.4 bước 4): hiện hộp xác nhận nêu lý do, yêu cầu chọn "Vẫn gửi (ghi lý do)" hoặc "Huỷ". Cấu hình cho phép **chặn cứng** với vi phạm nặng (ví dụ C1 gửi tin có liều cụ thể cho ca cụ thể). |
| UI-2.8 | "Chuyển": chọn người nhận trong danh sách người đang trực đủ cấp, kèm ghi chú bàn giao. "Đẩy cấp": chọn cấp cần thiết và lý do. |
| UI-2.9 | Thanh trạng thái: chọn online/away/offline. Khi đổi sang offline mà đang có cuộc chat thì hỏi chuyển giao. |
| UI-2.10 | Thông báo (âm thanh hoặc badge) khi có cuộc chat mới đủ cấp, khi được chỉ định, khi khách nhắn. |

## 3. Khung 3 – Quản lý

```
┌───────────────────────────────────────────────┬───────────────────────────┐
│ CHAT VỚI AGENT QUẢN LÝ          [⚡ Điều chỉnh nhanh] │ BẢNG TRẠNG THÁI        │
│ [Quản lý] Tóm tắt cuộc chat của A với B        │ Đang trực: 6 (C1:3 C2:2 C3:1)│
│ [Agent] ┌ TÓM TẮT CUỘC TRÒ CHUYỆN ┐            │ Chờ: 4 (1 quá SLA)         │
│         │ (form chuẩn, có liên kết)│           │ Đang xử lý: 9              │
│         └──────────────────────────┘           │ Hôm nay: 57 cuộc, FRT 2'10"│
│ [Quản lý] Nâng B lên C2                        │ ─────────────────────────  │
│ [Agent] ┌ ĐỀ XUẤT THAO TÁC ───────────┐        │ Cảnh báo:                  │
│         │ Cấp C2 cho B từ 17/11       │        │ • #A12 chờ 6' (C2, khẩn)   │
│         │ Lý do: ...                  │        │ • B gửi vượt quyền 1 lần   │
│         │ [Xác nhận] [Sửa] [Huỷ]      │        │                            │
│         └─────────────────────────────┘        │                            │
│ [Nhập yêu cầu .....................] [Gửi]     │                            │
│ Gợi ý nhanh: [Báo cáo hôm nay] [Chờ quá SLA]   │                            │
└───────────────────────────────────────────────┴───────────────────────────┘
```

| Mã | Yêu cầu |
|---|---|
| UI-3.1 | Khung chat với agent quản lý: hiển thị kết quả dạng **form chuẩn** (thẻ có cấu trúc), bảng, danh sách có liên kết mở cuộc chat (chỉ đọc). |
| UI-3.2 | Thao tác ghi do agent đề xuất hiển thị thành **thẻ đề xuất** gồm: hành động, đối tượng, giá trị cũ → mới, lý do, nút Xác nhận/Sửa/Huỷ. Chỉ khi bấm Xác nhận mới thực hiện. |
| UI-3.3 | Bảng trạng thái bên phải tự làm mới (≤ 10 giây): số người trực theo cấp, hàng chờ, cuộc chat quá SLA, cảnh báo vượt quyền. |
| UI-3.4 | Nút gợi ý nhanh cho các yêu cầu thường dùng. |
| UI-3.5 | Phiên chat của quản lý được lưu (xem 04), có thể mở lại và xuất form ra Markdown/PDF. |
| UI-3.6 | Mở cuộc chat bất kỳ ở chế độ chỉ đọc. Có nút "Chỉ định cho…" ngay trong màn xem. |

### 3.1 Popup "Điều chỉnh nhanh"

Mở từ khung 3. Dùng cho các thao tác thường gặp mà không cần rời khung chat.

| Tab | Nội dung |
|---|---|
| Người trực | Danh sách người đang trực/offline. Mỗi dòng: cấp hiện tại (đổi bằng menu), bật/tắt `ai.send_unedited`, số cuộc tối đa, trạng thái. |
| Chỉ định | Chọn cuộc chat đang chờ hoặc đang xử lý, chọn người nhận (lọc theo đủ cấp, đang online, còn chỗ). |
| Agent | Bật/tắt nhanh agent copilot theo cấp (ví dụ tạm tắt gợi ý C3), chuyển model dự phòng. |

- Mọi thay đổi trong popup đều yêu cầu nhập **lý do** (có thể chọn lý do mẫu) và được ghi nhật ký.
- Thay đổi cấp lên C2/C3 cho người chưa có chứng chỉ đã xác minh: popup **không cho phép**, mà dẫn tới trang phân quyền để xác minh.

## 4. Trang cấu hình model (quản trị)

| Khu vực | Nội dung |
|---|---|
| Danh sách agent | Mỗi agent (xem 03): provider (Ollama / Gemini / OpenAI-compatible), tên model, nhiệt độ, số token tối đa, bật/tắt, **model dự phòng** khi model chính lỗi. |
| Kiểm tra | Nút "Kiểm tra kết nối" và "Chạy thử": gửi một câu hỏi mẫu, hiện câu trả lời và thời gian. |
| Prompt | Xem prompt hiện hành của từng agent. Sửa prompt tạo **phiên bản mới**, có ghi chú thay đổi; có thể quay về phiên bản cũ. Sửa prompt của agent copilot cần quyền quản trị và hiện cảnh báo. |
| Embedding & tài liệu | Hiển thị model embedding và collection đang dùng **(chỉ đọc)**. Đổi embedding cần lập chỉ mục lại, nên tách thành thao tác riêng có cảnh báo. |
| Khóa API | Chỉ hiện trạng thái "đã cấu hình / chưa", không hiện giá trị khoá. |
| Lịch sử | Ai đổi gì, lúc nào. |

Thay đổi model hoặc prompt có hiệu lực với **tin nhắn tiếp theo**. Tin nhắn đang sinh dở vẫn dùng cấu hình cũ. Mỗi gợi ý và tin AI lưu kèm agent, phiên bản prompt và model đã dùng.

## 5. Trang cấu hình quyền (quản lý)

| Khu vực | Nội dung |
|---|---|
| Danh sách nhân sự | Tên, chức danh, cấp chuyên môn, các quyền thao tác, trạng thái tài khoản, hạn chứng chỉ. Lọc và tìm kiếm. |
| Chi tiết nhân sự | Thông tin chứng chỉ (loại, số, nơi cấp, ngày hết hạn, tệp scan), trạng thái xác minh (người xác minh, ngày). Cấp chuyên môn kèm ngày hiệu lực/hết hạn. Quyền thao tác. |
| Lịch sử quyền | Toàn bộ bản ghi cấp/thu hồi kèm lý do. |
| Mẫu quyền | Các bộ quyền mẫu, ví dụ "Dược sĩ mới (C1, không gửi nguyên gợi ý, tối đa 3 cuộc)", để áp nhanh. |
| Cảnh báo | Chứng chỉ sắp hết hạn trong 30 ngày; người trực có nhiều cảnh báo vượt quyền. |
