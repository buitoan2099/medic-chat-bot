# Hướng dẫn sử dụng hệ thống tư vấn thuốc 3 khung

Cập nhật: 19/11/2026 · Dành cho: người trực, quản lý, quản trị hệ thống

Hệ thống gồm 3 khung và 2 trang quản trị, mở từ thanh bên trái của trang web:

| Trang | Ai dùng | Để làm gì |
|---|---|---|
| **Home** (khung 1) | Người dân / khách | Hỏi AI về thuốc, hoặc chat với người trực |
| **Người trực** (khung 2) | Điều dưỡng, dược sĩ, bác sĩ trực | Nhận và trả lời cuộc chat, có gợi ý AI |
| **Quản lý** (khung 3) | Quản lý | Xem báo cáo, hỏi trợ lý AI, chỉ định cuộc chat, chỉnh quyền nhanh |
| **Phân quyền** | Quản lý | Cấp độ chuyên môn, chứng chỉ, quyền chi tiết của từng người |
| **Cấu hình model** | Quản trị (cần `ADMIN_TOKEN`) | Chọn model AI, sửa prompt, cài đặt, tạo chỉ mục tài liệu |

> **Nguyên tắc chung:** hệ thống **không kê đơn trực tuyến** ở bất kỳ cấp nào. AI chỉ trả lời thông tin có trong tài liệu (Dược thư Quốc gia 2018).

---

## 1. Khung 1 – Khách hỏi

1. Tick **Tôi đã đọc và đồng ý**, rồi chọn cách hỏi:
   - **🤖 AI (tra cứu tài liệu):** hỏi thông tin thuốc, ví dụ "Ketorolac là thuốc gì?". Câu trả lời có mục *Tài liệu tham khảo* ghi trang.
   - **🧑‍⚕️ Người trực:** nói chuyện với nhân viên y tế.
2. Có thể khai thêm tuổi, dị ứng, bệnh nền, thuốc đang dùng, hoặc bỏ trống. Bấm **Bắt đầu**. Đang chat với AI vẫn bấm **🧑‍⚕️ Chuyển sang người trực** được bất cứ lúc nào.
3. Trong lúc chờ có vòng xoay kèm số giây, cho biết đang làm bước nào:
   - với AI: *Đang phân loại câu hỏi → Đang tìm trong tài liệu → Đang soạn câu trả lời*;
   - với người trực: *Đang chờ người trực tiếp nhận…* hoặc *Dược sĩ Lan đang xem tin của bạn…*.
4. Khi hỏi AI:
   - Câu hỏi cần tư vấn riêng (ví dụ "tôi bị sốt nên uống gì?") thì AI **không tự trả lời** mà mời chuyển sang người trực.
   - Câu có dấu hiệu nguy hiểm (khó thở, đau ngực…) thì hiện **thẻ đỏ khuyên gọi 115**.
5. Cuộc chat đã kết thúc vẫn nhắn tiếp được trong **24 giờ**, và sẽ quay về người trực cũ nếu người đó còn trực.
6. Lưu **mã cuộc trò chuyện** để mở lại sau (ô *Mở lại bằng mã* ở thanh bên). Nút **➕ Cuộc trò chuyện mới** để bắt đầu lại.

Thời gian chờ thực tế trên máy hiện tại:
- AI bắt đầu trả lời sau khoảng **35–40 giây**, rồi chữ chạy ra dần;
- bước phân loại mất khoảng 12–15 giây.

---

## 2. Khung 2 – Người trực

### 2.1 Đăng nhập và bắt đầu ca

- **Chế độ chạy thử** (`DEMO_MODE` bật): chọn tài khoản có sẵn rồi bấm **Vào**, không cần mật khẩu.
  - Điều dưỡng An (C1), Dược sĩ Lan (C2), Bác sĩ Minh (C3).
  - Trang này chỉ liệt kê tài khoản người trực.
- **Chạy thật:** mở *Đăng nhập bằng tài khoản*, nhập tên đăng nhập và mật khẩu. Sai nhiều lần sẽ bị khoá tạm thời.
- Ở thanh bên, đặt trạng thái **🟢 Đang trực**. Chỉ khi đang trực mới nhận được cuộc chat.
- Muốn **Rời ca** khi còn cuộc chat đang phụ trách: hệ thống yêu cầu chuyển cho người khác, hoặc xác nhận trả cuộc chat về hàng chờ.

### 2.2 Cấp chuyên môn: được làm gì

| Cấp | Ai | Được tư vấn |
|---|---|---|
| **C1** | Điều dưỡng, nhân viên | Thông tin thuốc chung, hướng dẫn tự chăm sóc, khuyên đi khám. **Không** gợi ý thuốc cho ca cụ thể |
| **C2** | Dược sĩ (đã xác minh) | Thêm: tư vấn thuốc **không kê đơn** cho bệnh nhẹ |
| **C3** | Bác sĩ (đã xác minh giấy phép) | Thêm: đánh giá ca nặng hơn, **hẹn khám trực tiếp**. Vẫn **không kê đơn** |

### 2.3 Nhận cuộc chat

- **Hàng chờ** chỉ hiện các cuộc chat **đủ cấp** với bạn. Ca khẩn đứng trước, rồi đến ca chờ lâu.
- Bấm vào một cuộc chat để **tiếp nhận**. Nếu hai người bấm cùng lúc, chỉ một người nhận được.
- **Của tôi** liệt kê các cuộc chat bạn đang phụ trách, có giới hạn số cuộc tối đa, và các **đề nghị chuyển** người khác gửi cho bạn (Chấp nhận / Từ chối).

### 2.4 Trả lời khách

- **Cột giữa** gồm:
  - lịch sử chat (cả phần khách đã hỏi AI trước đó);
  - **Hồ sơ ca**: AI tự điền (🤖), bạn sửa và bấm Lưu (✔);
  - ô soạn tin.
- **Bấm 📨 Gửi là tin đi ngay.** Không còn bước AI kiểm tra trước khi gửi; quản trị bật lại được nếu cần (mục 5.3). Chỉ còn hai kiểm tra theo quy tắc, chạy tức thì:
  - tin có thuốc nằm trong **danh mục thuốc kê đơn** thì bị chặn;
  - tin có tên tài liệu hoặc số trang thì có cảnh báo. Câu trả lời cho khách **không được kèm trích dẫn**.

### 2.5 Gợi ý AI (cột phải)

- Khi khách nhắn, AI soạn **gợi ý trả lời theo đúng cấp** của bạn. Việc này mất khoảng **1 phút**. Trong lúc chờ có vòng xoay *Đang tạo gợi ý cho tin mới của khách… 25s*; gợi ý tự hiện khi xong.
- Gợi ý của tin trước được thu gọn trong mục **🕘 Gợi ý cho tin TRƯỚC của khách (cũ)**, để không gửi nhầm.
- Mỗi gợi ý có:
  - bản nháp trả lời, câu nên hỏi thêm, hướng dẫn theo dõi;
  - dấu hiệu nặng (nếu có), ghi chú nội bộ (không gửi khách), nguồn tài liệu để bạn đối chiếu.
- Các nút:
  - **Gửi luôn:** gửi nguyên văn. Cần có quyền "gửi nguyên gợi ý".
  - **Dùng & sửa:** đưa vào ô soạn để chỉnh rồi gửi.
  - **Bỏ:** bỏ gợi ý này.
  - **🔄 Tạo lại gợi ý:** có thể kèm chỉ dẫn, ví dụ "ngắn hơn, hỏi thêm cân nặng".
- ⛔ **Gợi ý vượt quyền** (ví dụ gợi ý thuốc khi bạn là C1) có khung đỏ và **không gửi được** dưới mọi hình thức. Bạn vẫn **tự soạn trả lời** bình thường, hoặc dùng **⬆️ Đẩy cấp**.

### 2.6 Chuyển, đẩy cấp, đóng

| Nút | Khi nào | Điều gì xảy ra |
|---|---|---|
| **↪️ Chuyển** | Nhờ một người trực khác đang online | Người nhận phải **chấp nhận** thì mới chuyển |
| **⬆️ Đẩy cấp** | Ca vượt cấp của bạn | Cuộc chat về hàng chờ với cấp cao hơn (C2/C3), bắt buộc ghi lý do; khách được báo đang chuyển chuyên viên |
| **✅ Đóng** | Đã xong | Khách nhắn lại trong 24 giờ thì cuộc chat mở lại cho bạn |

---

## 3. Khung 3 – Quản lý

Đăng nhập bằng tài khoản quản lý. Ở chế độ chạy thử là *Quản lý Hà*; trang này chỉ liệt kê tài khoản quản lý. Mỗi khung giữ phiên đăng nhập riêng, nên cùng một trình duyệt mở được cả khung người trực lẫn khung quản lý.

### 3.1 Báo cáo nhanh (không cần AI, ra ngay)

| Nút | Báo cáo |
|---|---|
| **Báo cáo hôm nay / 7 ngày** | F-4 vận hành: số cuộc chat, thời gian phản hồi, hàng chờ, vi phạm |
| **So sánh** | F-5 so sánh các người trực hôm nay (không xếp hạng chuyên môn) |
| **Quá SLA** | Cuộc chat chờ quá hạn (mặc định 5 phút; ca khẩn 1 phút) |
| **Người trực… → 📝 Nội dung đã xử lý (F-6)** | Từng cuộc chat người đó xử lý: khách hỏi gì, đã trả lời gì, kết quả, chuyển hay đẩy cấp, lưu ý |
| **Người trực… → 📊 Số liệu hiệu suất (F-2)** | Số cuộc, thời gian phản hồi, tỉ lệ dùng gợi ý AI… |
| **Người trực… → 🤖 Nhờ AI tóm tắt & nhận xét** | F-6 kèm nhận xét của AI: nhóm vấn đề, ca cần xem lại (mất 1–2 phút) |

Mỗi thẻ báo cáo có nút **⬇️ Tải Markdown**.

### 3.2 Hỏi trợ lý quản lý (AG-7)

Gõ câu hỏi tự nhiên vào ô chat, ví dụ:
- "Hôm nay Lan xử lý những gì?" (F-6)
- "Hiệu suất của Minh tuần này?" (F-2), rồi "còn An thì sao?" (trợ lý hiểu câu nối tiếp)
- "Tóm tắt cuộc chat 23SPEY" (F-1), "Đánh giá chất lượng cuộc chat 23SPEY" (F-3)
- "Chống chỉ định của diclofenac?" (trả lời có trích trang tài liệu)
- "Nâng Lan lên C2": trợ lý chỉ **tạo đề xuất**, bạn phải bấm **✅ Xác nhận** trên thẻ thì mới có hiệu lực.

Số liệu trong thẻ do **hệ thống tính**, không phải AI tự đặt ra. Phần *Nhận định (AI)* cần quản lý thẩm định.

### 3.3 Điều chỉnh nhanh (⚡)

- **Người trực:** đổi cấp, quyền gửi nguyên gợi ý, số cuộc chat tối đa. Bắt buộc ghi lý do. Muốn nâng lên C2/C3 thì phải xác minh chứng chỉ ở trang Phân quyền trước.
- **Chỉ định:**
  - *Đang chờ:* giao một cuộc chat trong hàng chờ cho người trực.
  - *Đang xử lý (thay người trực):* chọn cuộc chat đang dở và người thay. Có thể **nâng cấp cần thiết** của cuộc chat lên C2/C3 cùng lúc.
  - Khách thấy "Bác sĩ Minh sẽ tiếp tục hỗ trợ bạn…", và người trực cũ không gửi được tin vào cuộc đó nữa.
  - Giao cho người chưa đủ cấp thì phải tick xác nhận và ghi lý do.
- **Agent:** bật/tắt từng agent AI, đặt model dự phòng.

### 3.4 Bảng trạng thái (cột phải, tự làm mới)

Gồm: số người đang trực theo cấp, số cuộc đang chờ và đang xử lý, các chỉ số hôm nay, danh sách chờ (bấm vào để xem nội dung).

---

## 4. Trang Phân quyền (quản lý)

- Danh sách nhân sự: cấp, trạng thái trực, chứng chỉ và hạn chứng chỉ (cảnh báo trước 30 ngày).
- **Xác minh chứng chỉ:** dược sĩ cho C2, bác sĩ cho C3. Chưa xác minh thì không nâng cấp được.
- Cấp hoặc thu hồi từng quyền. Bảng lịch sử quyền ghi thời hạn hiệu lực. Muốn đặt quyền **có thời hạn** (ví dụ cho C2 trong 1 tuần), nhờ trợ lý quản lý tạo đề xuất rồi xác nhận.
- Áp **mẫu quyền** (ví dụ "Dược sĩ mới": C1, phải sửa gợi ý trước khi gửi, tối đa 3 cuộc).
- Mọi thay đổi đều bắt buộc ghi lý do và được lưu nhật ký.

---

## 5. Trang Cấu hình model (quản trị)

Nhập `ADMIN_TOKEN` (trong file `.env`) để vào.

### 5.1 Agent và model

| Agent | Việc | Ghi chú |
|---|---|---|
| AG-0 | Phân loại câu hỏi (ý định, cấp cần thiết, khẩn) | Quy tắc cấp cứu chạy trước, rồi đến AI |
| AG-1 | Trả lời khách ở chế độ AI | Chỉ theo tài liệu, có trích trang |
| AG-2 / AG-3 / AG-4 | Gợi ý cho người trực C1 / C2 / C3 | Mỗi cấp một prompt riêng |
| AG-5 | Tóm tắt và điền hồ sơ ca | Chạy nền, sau gợi ý |
| AG-6 | Kiểm tra trước khi gửi | **Mặc định tắt** |
| AG-7 | Trợ lý quản lý | Chỉ đọc dữ liệu và tạo đề xuất |

Với từng agent có thể: đổi model, nhiệt độ, thời gian chờ; đặt model dự phòng; **thử nhanh**; sửa prompt (lưu thành phiên bản mới, quay lại bản cũ được).

### 5.2 Chỉ mục tài liệu

- **Tạo lại chỉ mục:** tạo bản mới song song; khi xong thì chuyển sang, và **quay lại** bản cũ được.
- **Tiếp tục** nếu lần tạo trước bị ngắt (không phải làm lại từ đầu). Có tiến độ, tốc độ và thời gian còn lại.
- Khi chỉ mục chưa sẵn sàng, Home hiện banner; hệ thống vẫn tìm được bằng từ khoá.

### 5.3 Cài đặt quan trọng

| Cài đặt | Mặc định | Ý nghĩa |
|---|---|---|
| `guard_llm_enabled` | `false` | Bật AI kiểm tra (AG-6) trước khi gửi. Đang tắt để gửi tức thì. **Lưu ý:** danh mục thuốc kê đơn còn rỗng, nên khi tắt thì tin có thuốc kê đơn **không bị chặn** |
| `sla_normal_s` / `sla_emergency_s` | 300 / 60 | Ngưỡng cảnh báo chờ (giây) |
| `reopen_window_h` | 24 | Thời gian khách nhắn lại thì mở lại cuộc chat |
| `llm_max_parallel` | 1 | Số yêu cầu Ollama chạy cùng lúc. Phải khớp `OLLAMA_NUM_PARALLEL` trên máy chạy Ollama |
| `llm_reserved_slots` | 1 | Số chỗ giữ cho việc gấp khi `llm_max_parallel ≥ 2` |
| `top_k` | 5 | Số đoạn tài liệu đưa vào câu trả lời |
| `permission_templates` | 2 mẫu | Mẫu quyền áp nhanh |

---

## 6. Câu hỏi thường gặp

**AI trả lời chậm, dù đã có RAG?**
RAG chỉ tìm đoạn tài liệu, mất dưới 1 giây. Thời gian chủ yếu nằm ở model `qwen3:14b` trên Mac mini: đọc khoảng 3.600 token mất ~30 giây, viết câu trả lời khoảng 10 token/giây. Máy chỉ chạy một yêu cầu mỗi lúc, nên khi đang tạo gợi ý thì các việc khác phải chờ.

**Không thấy gợi ý AI?**
Đợi khoảng 1 phút, có vòng xoay *Đang tạo gợi ý*. Nếu không có vòng xoay, kiểm tra quyền "dùng gợi ý AI" và xem agent của cấp mình có đang bật không.

**Gợi ý có khung đỏ "vượt quyền"?**
Không gửi được gợi ý đó. Hãy tự trả lời trong phạm vi cấp mình, hoặc đẩy cấp.

**Khách nói đã nhắn mà người trực không thấy?**
Kiểm tra người trực đã bật 🟢 Đang trực chưa, và cấp có đủ với cuộc chat không (hàng chờ chỉ hiện ca đủ cấp). Quản lý xem được mọi cuộc chat trong *Quá SLA* hoặc trên bảng trạng thái.
