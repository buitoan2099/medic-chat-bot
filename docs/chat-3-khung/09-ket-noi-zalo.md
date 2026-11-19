# 09 – Kế hoạch kết nối Zalo (qua zca-js)

Trạng thái: **kế hoạch, chưa triển khai** · Ngày: 19/11/2026

## 1. Mục tiêu

- Quản lý gắn một hoặc nhiều **tài khoản Zalo** cho người trực.
- Khi có người nhắn tới tài khoản Zalo đó, hệ thống tạo (hoặc nối tiếp) một **cuộc chat** trong khung 2.
- Người trực được gắn với tài khoản tiếp nhận rồi trả lời ngay trên khung 2. Tin trả lời được gửi đi **từ chính tài khoản Zalo đó**.
- Giữ nguyên các chức năng hiện có cho cuộc chat từ Zalo:
  - gợi ý AI theo cấp, chặn gợi ý vượt quyền;
  - hồ sơ ca (AG-5), chuyển, đẩy cấp, chỉ định;
  - báo cáo F-1…F-6 của quản lý.

## 2. Cần chốt trước: rủi ro của zca-js

zca-js ([github.com/RFS-ADRENO/zca-js](https://github.com/RFS-ADRENO/zca-js), giấy phép MIT) là thư viện **không chính thức**. Nó giả lập Zalo Web trên **tài khoản cá nhân**.

| Rủi ro | Mức | Ghi chú |
|---|---|---|
| **Tài khoản bị khoá** | Cao | README của thư viện cảnh báo tài khoản có thể bị khoá; nhóm phát triển không chịu trách nhiệm. Gửi nhiều, gửi nhanh hoặc giống bot thì càng dễ bị khoá. |
| **Vi phạm điều khoản Zalo** | Cao | Dùng client không chính thức. Không phù hợp để chạy chính thức cho một cơ sở y tế. |
| **Thư viện hỏng khi Zalo đổi giao thức** | Trung bình | Không có cam kết ổn định. Phải theo dõi phiên bản và có phương án dự phòng. |
| **Mỗi tài khoản chỉ một listener** | Trung bình | Mở Zalo Web trên trình duyệt sẽ làm listener dừng. Người trực vẫn dùng app điện thoại được, nhưng **không được mở Zalo Web** bằng tài khoản này. |
| **Phiên đăng nhập hết hạn** | Trung bình | Phải đăng nhập lại bằng QR. Cần cảnh báo cho quản lý. |
| **Dữ liệu cá nhân (NĐ 13/2023)** | Cao | Tên, ảnh và nội dung sức khoẻ từ Zalo đi vào hệ thống. Cần thông báo và đồng ý (mục 6.4). |

**Đề xuất:**
- zca-js **chỉ dùng cho thử nghiệm** (pilot), với **tài khoản Zalo riêng cho công việc** (SIM riêng), không dùng tài khoản cá nhân của nhân viên.
- Khi vận hành thật, chuyển sang **Zalo Official Account (OA)**, là API chính thức cho doanh nghiệp. Cần kiểm tra lại điều kiện và giới hạn gửi tin của OA tại thời điểm đăng ký.
- Thiết kế ở dưới tách **lớp kênh (channel)** riêng, để sau này thay zca-js bằng OA mà không phải sửa nghiệp vụ.

## 3. Kiến trúc

```
Khách (app Zalo) ⇄ máy chủ Zalo ⇄ [zalo-bridge: Node + zca-js]  ⇄ HTTP nội bộ ⇄ [backend FastAPI] ⇄ Streamlit khung 2/3
                                    · giữ phiên đăng nhập             · lưu trữ, định tuyến
                                    · listener nhận tin               · gợi ý AI, quyền, báo cáo
                                    · gửi tin (có giới hạn tốc độ)    · outbox tin đi
```

- **zalo-bridge** là một tiến trình **Node.js riêng**, vì zca-js là thư viện JavaScript. Mỗi máy chạy một tiến trình, giữ được nhiều tài khoản.
  - Nó **không** đụng tới Qdrant hay thư mục `storage/`, nên không vi phạm quy tắc R1/R2 (chỉ backend mở Qdrant và giữ dữ liệu).
  - Thông tin đăng nhập (cookie, imei, user-agent) nằm trong thư mục dữ liệu riêng của bridge, được mã hoá và đưa vào `.gitignore`. Backend chỉ biết trạng thái kết nối.
- **Giao tiếp hai chiều** chỉ chạy trên `127.0.0.1`, kèm khoá bí mật dùng chung `BRIDGE_TOKEN`:
  - *Tin đến:* bridge gọi `POST /api/channels/zalo/inbound`. Có **chống trùng** theo `msg_id`, vì Zalo hoặc bridge có thể gửi lại.
  - *Tin đi:* backend ghi vào **outbox**; bridge lấy tin cần gửi, gửi rồi báo kết quả qua `POST /api/channels/zalo/ack`. Nếu bridge đang tắt, tin vẫn nằm trong outbox và tự gửi lại khi bridge chạy lại.
  - *Trạng thái tài khoản:* bridge báo `connected`, `needs_login` hoặc `error`. Khi cần đăng nhập, bridge đưa mã QR để quản lý quét trên trang quản trị.
- **Giới hạn tốc độ gửi** cho mỗi tài khoản (ví dụ ≥ 2 giây giữa hai tin, tối đa N tin/phút) để giảm nguy cơ bị khoá.

## 4. Mô hình dữ liệu (bổ sung vào 04)

| Thực thể | Trường mới | Ý nghĩa |
|---|---|---|
| **ChannelAccount** *(mới)* | `id`, `channel='zalo'`, `display_name`, `external_uid`, `status`, `primary_staff_id`, `backup_staff_ids`, `auto_reply_offline`, `active` | Một tài khoản Zalo và người trực được gắn với nó |
| **EndUser** | `channel`, `channel_account_id`, `external_user_id`, `external_name` | Khách Zalo; ghép theo (tài khoản, mã người dùng Zalo) |
| **Conversation** | `channel` (`web` \| `zalo`), `channel_account_id`, `external_thread_id` | Cuộc chat Zalo luôn đi ra qua đúng tài khoản đã nhận |
| **Message** | `external_id`, `delivery` (`pending` \| `sent` \| `failed`), `origin` (`panel` \| `phone`) | Chống trùng, trạng thái gửi, tin gõ trên app điện thoại |
| **OutboxMessage** *(mới)* | `message_id`, `account_id`, `thread_id`, `text`, `attempts`, `last_error`, `next_try_at` | Hàng đợi tin đi |

Tất cả đi qua lớp repository như dữ liệu hiện có, lưu theo ngày.

## 5. Luồng nghiệp vụ

### 5.1 Khách nhắn vào tài khoản Zalo A

1. Bridge nhận tin rồi gọi `inbound`. Backend tìm cuộc chat của cặp (A, khách):
   - **đang mở** (chờ hoặc đang xử lý): nối tin vào cuộc đó;
   - **đã đóng trong vòng 24 giờ**: mở lại cho người cũ (BR-06);
   - **còn lại**: tạo cuộc chat mới, `mode=human`, `channel=zalo`.
2. **Kiểm tra cấp cứu bằng quy tắc** (không dùng LLM, như `rules/emergency_minimal.json`):
   - đánh dấu khẩn;
   - có thể tự gửi lời khuyên gọi 115 (cài đặt, mặc định **bật**).
3. **Định tuyến:**
   - cuộc chat vào hàng chờ, nhưng **chỉ hiện cho người trực được gắn với A** (người chính và người dự phòng) và quản lý;
   - nếu người chính đang trực thì **tự giao** (cài đặt, mặc định **tắt**: người trực tự bấm tiếp nhận, đúng như mô tả yêu cầu).
4. Phân loại AG-0 xác định cấp cần thiết, giống chế độ người trực trên web. AG-0 chạy nền, không làm chậm việc tạo cuộc chat.
5. Gợi ý AI (AG-2/3/4) và hồ sơ ca (AG-5) chạy như hiện tại.

### 5.2 Người trực trả lời

- Gửi từ khung 2: tin được ghi vào outbox, bridge gửi qua tài khoản A. Khung 2 hiện trạng thái ✓ đã gửi hoặc ⚠ lỗi kèm nút **gửi lại**.
- Khách thấy tin từ **tên tài khoản Zalo A**, không thấy tên người trực. Có thể bật **tiền tố tên** (ví dụ `[DS Lan]`) bằng cài đặt.
- **Trả lời trực tiếp trên app điện thoại:**
  - bridge nhận được tin có `isSelf`, ghi vào cuộc chat là tin của người trực, `origin=phone`;
  - tin này không qua kiểm tra gợi ý; báo cáo F-6 vẫn thấy.
- **Chỉ gửi văn bản** ở giai đoạn đầu. Tin đến là ảnh hoặc sticker sẽ hiện dạng "[ảnh] (xem trên Zalo)". Ảnh gửi đi để giai đoạn sau.

### 5.3 Chuyển, đẩy cấp, chỉ định

- Tin đi **luôn qua tài khoản A**, bất kể ai đang phụ trách. Vì vậy:
  - chuyển hoặc chỉ định cho người trực khác vẫn hoạt động; người nhận trả lời thay, khách vẫn thấy cùng tài khoản A;
  - đẩy cấp đưa cuộc chat về hàng chờ của A. Nếu không ai được gắn với A đủ cấp, cuộc chat **mở rộng ra hàng chờ chung** của cấp đó và quản lý được báo.
- Quản lý chỉ định được cho bất kỳ người trực nào, kể cả người không gắn với A.

### 5.4 Ngoài giờ, tài khoản mất kết nối

- Không ai được gắn với A đang trực:
  - tự trả lời một lần, nội dung cấu hình được (ví dụ "Hiện ngoài giờ trực, chúng tôi sẽ phản hồi lúc …");
  - SLA tính như hàng chờ thường.
- Tài khoản ở trạng thái `needs_login` hoặc `error`:
  - khung 3 hiện cảnh báo đỏ;
  - tin đi giữ trong outbox, không bị mất.

## 6. Xung đột với kiến trúc và đặc tả hiện tại

| # | Xung đột | Đề xuất |
|---|---|---|
| Z-1 | Hệ thống hiện chỉ có **một tiến trình backend Python**; zca-js là Node | Thêm tiến trình `zalo-bridge` riêng, chỉ nói chuyện với backend qua HTTP nội bộ; không chạm Qdrant hay `storage/` (giữ R1/R2) |
| Z-2 | Khung 1 bắt **đồng ý (consent)** trước khi chat; khách Zalo không qua bước này | Tin đầu tiên của mỗi khách mới tự gửi **thông báo xử lý dữ liệu** kèm liên kết chính sách; ghi `consent_at` khi khách nhắn tiếp. Cần pháp chế duyệt nội dung (Q-Z5) |
| Z-3 | Cuộc chat hiện **bắt đầu ở chế độ AI** | Zalo vào thẳng chế độ người trực. Không cho AI tự trả lời khách ở giai đoạn đầu |
| Z-4 | Người dùng khung 1 định danh theo trình duyệt | Khách Zalo định danh theo (tài khoản, mã người dùng Zalo); không gộp với khách web |
| Z-5 | Gửi tin hiện **đồng bộ** (lưu xong là khách thấy) | Tin Zalo có trạng thái gửi (outbox), khung 2 hiện đã gửi / lỗi |
| Z-6 | Tin của người trực mang tên người trực (UI-1.6) | Trên Zalo, khách thấy tên tài khoản; tiền tố tên là tuỳ chọn |
| Z-7 | Báo cáo coi mọi tin của người trực là gửi từ khung 2 | Thêm `origin=phone`. Thời gian phản hồi vẫn tính, cột "dùng gợi ý AI" không áp dụng |

## 7. Giao diện

- **Khung 2:**
  - huy hiệu kênh `Zalo · <tên tài khoản>` ở hàng chờ và tiêu đề cuộc chat;
  - trạng thái gửi từng tin, nút gửi lại;
  - bộ lọc "chỉ tài khoản của tôi".
- **Khung 3:**
  - bảng trạng thái hiện số tài khoản Zalo đang kết nối hoặc mất kết nối;
  - báo cáo F-4/F-6 tách số liệu theo kênh.
- **Trang "Kênh Zalo"** (mới, chỉ quản lý hoặc admin):
  - danh sách tài khoản và trạng thái;
  - **quét QR đăng nhập**;
  - gắn người trực chính và dự phòng;
  - bật/tắt tự giao, trả lời ngoài giờ, tiền tố tên;
  - giới hạn tốc độ gửi;
  - mọi thay đổi đều ghi nhật ký kèm lý do.

## 8. Lộ trình

| Giai đoạn | Nội dung | Ước lượng | Điều kiện qua |
|---|---|---|---|
| **Z0 – Thử nghiệm kỹ thuật** | Bridge tối thiểu: đăng nhập QR, nhận và gửi văn bản, lưu phiên, tự kết nối lại; chạy 3–5 ngày với tài khoản thử | 2–3 ngày | Không bị khoá; phiên giữ ≥ 24 giờ; mất kết nối thì báo được |
| **Z1 – Lớp kênh ở backend** | ChannelAccount, trường kênh, `inbound` (chống trùng), outbox, định tuyến theo tài khoản, quy tắc cấp cứu; test với bridge giả lập | 3–4 ngày | Test tự động cho luồng 5.1–5.4 |
| **Z2 – Bridge hoàn chỉnh** | Nhiều tài khoản, giới hạn tốc độ, tin từ điện thoại (`isSelf`), ảnh và sticker dạng chú thích, mã hoá phiên, giám sát | 3–4 ngày | Chạy thử đầy đủ với 1 tài khoản |
| **Z3 – Giao diện** | Trang Kênh Zalo (QR, gắn người trực), huy hiệu và trạng thái gửi ở khung 2, cảnh báo ở khung 3 | 2–3 ngày | Quản lý tự làm được từ đầu đến cuối |
| **Z4 – Thí điểm** | 1 tài khoản, 1–2 người trực, 1–2 tuần; đo thời gian phản hồi, lỗi gửi, sự cố phiên | 1–2 tuần | Quyết định: tiếp tục, hay chuyển sang Zalo OA |

Tổng phần làm: khoảng **2–3 tuần**, chưa tính thời gian thí điểm.

## 9. Kiểm thử

- **Bridge giả lập** (Python, trong `tests/`) đóng vai Zalo để kiểm tra:
  - nhận trùng tin;
  - tin đến khi cuộc chat đã đóng ≤ 24 giờ và > 24 giờ;
  - định tuyến theo tài khoản;
  - outbox: lỗi rồi gửi lại;
  - tin từ điện thoại;
  - khách có dấu hiệu cấp cứu.
- **Test hợp đồng API** `inbound`, `ack`, trạng thái (chạy chung với bộ pytest hiện có).
- **Thử tay ở Z0/Z4** với tài khoản thật, có checklist.

## 10. Câu hỏi cần trả lời

| # | Câu hỏi | Gợi ý |
|---|---|---|
| Q-Z1 | Chấp nhận rủi ro khoá tài khoản của zca-js cho thí điểm, hay đi thẳng Zalo OA? | zca-js cho thí điểm với tài khoản công việc riêng; OA khi chạy thật |
| Q-Z2 | Một tài khoản Zalo gắn **một** hay **nhiều** người trực? | Một người chính + dự phòng |
| Q-Z3 | Tin mới tự giao cho người chính, hay vào hàng chờ để tự tiếp nhận? | Hàng chờ (theo yêu cầu); tự giao là tuỳ chọn |
| Q-Z4 | Có cho AI tự trả lời khách Zalo (ví dụ ngoài giờ) không? | Chưa; chỉ tin ngoài giờ cố định |
| Q-Z5 | Nội dung thông báo xử lý dữ liệu và đồng ý cho khách Zalo | Cần pháp chế duyệt |
| Q-Z6 | Khách thấy tên tài khoản, hay thêm tiền tố tên người trực? | Thêm tiền tố để minh bạch người tư vấn |
| Q-Z7 | Có cần gửi ảnh, tệp trong giai đoạn đầu không? | Không; chỉ văn bản |
