# 01 · Nghiệp vụ

## 1. Vai trò

| Vai trò | Mô tả | Truy cập |
|---|---|---|
| Người dùng (khách) | Hỏi về thuốc và sức khoẻ | Khung 1 |
| Người trực | Nhân viên y tế: dược sĩ, điều dưỡng, bác sĩ… | Khung 2 |
| Quản lý | Giám sát, chỉ định, phân quyền, xem báo cáo | Khung 3, trang phân quyền |
| Quản trị | Cấu hình model, tài khoản, prompt | Trang cấu hình model, quản lý tài khoản |

Một tài khoản nhân sự có thể có nhiều vai trò. Ví dụ quản lý vẫn có thể trực nếu được cấp cấp quyền chuyên môn.

## 2. Cấp quyền chuyên môn của người trực

Ba cấp, **lũy tiến**: cấp cao hơn có toàn bộ quyền của cấp thấp hơn. Cấp quyền ứng với **tầng ca** T1/T2/T3 trong [../phan-tang.md](../phan-tang.md).

> **Hệ thống không kê đơn trực tuyến** ở bất kỳ cấp nào, kể cả bác sĩ (quyết định 17/11/2026). Ca cần thuốc kê đơn được chuyển T3-Chuyển: bác sĩ tư vấn và hẹn khám trực tiếp.

| Cấp | Tên | Được phép | Không được phép | Điều kiện cấp |
|---|---|---|---|---|
| **C1** | Tư vấn thông tin thuốc | Giải thích công dụng, cách dùng thông thường, tác dụng phụ, tương tác, bảo quản theo tài liệu. Tư vấn chung về bệnh (là gì, dấu hiệu, khi nào cần đi khám). | Chẩn đoán bệnh cụ thể cho khách. Đề xuất thuốc hay liều cho trường hợp cụ thể. Đưa phác đồ. | Tài khoản nhân sự đang hoạt động |
| **C2** | Đánh giá & tư vấn thuốc không kê đơn cho bệnh nhẹ (tầng T2) | Mọi quyền C1. Với ca thuộc **danh mục T2** ([phan-tang.md](../phan-tang.md) mục 3): đánh giá sơ bộ, hướng dẫn chăm sóc tại nhà, tư vấn thuốc **không kê đơn**. **Bắt buộc** kèm hướng dẫn theo dõi, dấu hiệu phải đến cơ sở y tế. | Gợi ý thuốc kê đơn. Ca ngoài danh mục T2, thuộc nhóm loại trừ, hoặc có tiêu chí T3: đẩy lên C3 hoặc khuyên đi khám. | Chứng chỉ chuyên môn y/dược (ví dụ dược sĩ, y sĩ…) đã được quản lý xác minh |
| **C3** | Bác sĩ tư vấn ca nặng (tầng T3-Chuyển) | Mọi quyền C2. Với ca **T3-Chuyển**: tư vấn, giải thích tình trạng và lý do cần khám, hướng dẫn chăm sóc/sơ cứu trong lúc chờ, **hẹn khám trực tiếp trong 24 giờ**. | Kê đơn trực tuyến. Đưa phác đồ điều trị để người bệnh tự áp dụng. Xử lý tại chỗ ca T3-Khẩn (hệ thống tự hướng dẫn gọi 115). | **Bác sĩ** có giấy phép hành nghề còn hiệu lực, đã được xác minh |

Danh mục bệnh nhẹ (T2), tiêu chí ca nặng (T3) và các ngưỡng số là **nội dung chuyên môn**, nằm trong [../phan-tang.md](../phan-tang.md) và cần Hội đồng chuyên môn duyệt trước khi vận hành (Q-1). Sau khi duyệt, chúng được lưu thành bộ quy tắc có phiên bản, không viết cứng trong code.

### 2.1 Quyền thao tác (độc lập với cấp chuyên môn)

| Mã quyền | Mô tả | Mặc định |
|---|---|---|
| `chat.claim` | Tự tiếp nhận cuộc chat trong hàng chờ | Bật |
| `chat.transfer` | Chuyển cuộc chat cho người trực khác | Bật |
| `chat.escalate` | Đẩy lên cấp chuyên môn cao hơn | Bật |
| `chat.view_all` | Xem (chỉ đọc) cuộc chat của người khác | Tắt |
| `ai.use_copilot` | Dùng gợi ý từ agent | Bật |
| `ai.send_unedited` | Gửi gợi ý mà không sửa | Bật (quản lý có thể tắt với người mới) |
| `chat.max_concurrent` | Số cuộc chat tối đa cùng lúc | 5 |

### 2.2 Hiệu lực và lịch sử quyền
- Mỗi lần cấp hoặc thu hồi quyền lưu thành một bản ghi riêng: ai cấp, lúc nào, lý do, hiệu lực từ/đến.
- Quyền có thể có **ngày hết hạn**, ví dụ gắn với hạn chứng chỉ hành nghề. Hết hạn thì tự hạ về cấp cao nhất còn hiệu lực.
- Hạ quyền khi người trực đang xử lý cuộc chat vượt quyền mới: cuộc chat đó tự đánh dấu cần chuyển, và quản lý nhận thông báo.

## 3. Luồng nghiệp vụ

### 3.1 Người dùng bắt đầu chat (khung 1)

1. Người dùng mở khung 1 và đọc, đồng ý **thông báo** gồm:
   - đây là kênh hỗ trợ tham khảo, không thay thế khám bệnh;
   - dữ liệu cuộc chat được lưu;
   - cấp cứu thì gọi 115.
2. Chọn chế độ:
   - **Chat với AI:** trả lời ngay từ tài liệu.
   - **Chat với người trực:** vào hàng chờ.
3. Tuỳ chọn: khai báo thông tin giúp tư vấn (tuổi, giới, đang mang thai/cho con bú, dị ứng thuốc, bệnh nền). Thông tin này lưu vào **hồ sơ ca** của cuộc chat.
4. Trong cuộc chat, người dùng có thể chuyển AI → người trực bất cứ lúc nào. Toàn bộ lịch sử phía AI được chuyển theo để người trực đọc.

### 3.2 Chế độ AI

```
câu hỏi ─► Agent phân loại ─► thông tin tài liệu ─► Agent AI người dùng (RAG) ─► trả lời
                         ├─► chẩn đoán / kê thuốc / phác đồ ─► từ chối + nút "Chat với người trực"
                         └─► dấu hiệu cấp cứu ─► hướng dẫn gọi 115 / đến cơ sở y tế ngay
```

- Agent AI người dùng **chỉ dùng nội dung trong tài liệu**. Không đủ căn cứ thì nói rõ.
- Mọi câu hỏi kiểu "tôi bị X thì uống gì", "liều cho con tôi 2 tuổi", "đây có phải bệnh Y không" đều được hướng sang người trực.

### 3.3 Chế độ người trực: tiếp nhận và chỉ định

```
Người dùng chọn "người trực"
        │
        ▼
 Agent phân loại ước lượng CẤP CẦN THIẾT (C1/C2/C3) + độ khẩn
        │
        ▼
 Hàng chờ ── người trực đủ cấp tự "Tiếp nhận" ──┐
        │                                       ├─► Cuộc chat có 1 người phụ trách
        └── quản lý "Chỉ định" cho người trực ──┘
```

**Quy tắc:**
- BR-01: Mỗi cuộc chat tại một thời điểm có **đúng một** người phụ trách. Tiếp nhận dùng cơ chế khoá: hai người bấm cùng lúc thì chỉ một người thành công, người còn lại nhận thông báo.
- BR-02: Hàng chờ chỉ hiện cho người trực **đủ cấp** so với cấp cần thiết ước lượng. Quản lý thấy toàn bộ.
- BR-03: Quản lý chỉ định được cho người trực **đang trực** và còn dưới giới hạn số cuộc chat. Chỉ định người không đủ cấp phải xác nhận thêm một bước và ghi lý do.
- BR-04: Người trực có thể **chuyển** cuộc chat cho người khác (cần người nhận chấp nhận), hoặc **đẩy cấp** khi câu hỏi vượt quyền: cuộc chat quay lại hàng chờ với cấp cần thiết cao hơn.
- BR-05: Cuộc chat chờ quá **thời gian SLA** chưa có người nhận thì quản lý được cảnh báo. SLA cấu hình được, mặc định 5 phút; ca khẩn là 1 phút.
- BR-06: Người trực đóng cuộc chat khi xong việc. Người dùng nhắn lại trong vòng 24 giờ thì cuộc chat **mở lại** với cùng người phụ trách nếu người đó đang trực; nếu không thì vào hàng chờ. Sau 24 giờ thì tạo cuộc chat mới, có liên kết tới cuộc trước.
- BR-07: Mỗi thay đổi (tiếp nhận, chỉ định, chuyển, đẩy cấp, đóng, mở lại) được ghi thành **sự kiện** có thời điểm và người thực hiện. Đây là nguồn dữ liệu tính hiệu suất.

### 3.4 Người trực trả lời với gợi ý của agent (khung 2)

1. Tin nhắn mới của khách đến, hệ thống tự gọi **agent copilot ứng với cấp của người trực**. Đầu vào gồm:
   - toàn bộ lịch sử cuộc chat (cả phần chat với AI trước đó);
   - hồ sơ ca;
   - đoạn tài liệu liên quan (RAG).
2. Gợi ý hiển thị cho người trực, gồm:
   - bản nháp trả lời khách: **không trích dẫn**, văn phong gửi khách;
   - ghi chú nội bộ chỉ người trực thấy: lý do, nguồn tài liệu kèm trang, cảnh báo;
   - nếu có: cảnh báo **vượt quyền**, kèm đề xuất đẩy cấp; cảnh báo **dấu hiệu nặng/cấp cứu**.
3. Người trực chọn một trong các cách:
   - **Gửi luôn** (cần quyền `ai.send_unedited`);
   - **Sửa rồi gửi**;
   - **Bỏ gợi ý**, tự viết;
   - **Tạo lại gợi ý**, có thể kèm chỉ dẫn, ví dụ "ngắn hơn", "hỏi thêm về tiền sử dị ứng".
4. Trước khi gửi, hệ thống **kiểm tra tin cuối cùng**:
   - tin gợi ý thuốc kê đơn cho trường hợp cụ thể (mọi cấp) thì **chặn**;
   - tin chẩn đoán/tư vấn điều trị vượt cấp người trực thì chặn hoặc yêu cầu xác nhận, tuỳ cấu hình;
   - tin chứa mẫu trích dẫn tài liệu (tên file, số trang) thì cảnh báo.
5. Lưu lại cả gợi ý và tin đã gửi, cùng cách người trực xử lý (gửi nguyên / sửa / bỏ). Dữ liệu này phục vụ đánh giá hiệu suất và chất lượng agent.

- BR-08: Câu trả lời gửi khách ở chế độ người trực **không chứa trích dẫn tài liệu**. Nguồn chỉ hiện ở ghi chú nội bộ.
- BR-08a: **Không kê đơn trực tuyến.** Tin gợi ý thuốc kê đơn cho trường hợp cụ thể bị kiểm tra trước khi gửi **chặn** ở mọi cấp. Được giải thích thông tin chung về thuốc kê đơn và cách dùng thuốc kê đơn khách đang dùng theo đơn sẵn có, nhưng không khuyên đổi liều hay ngừng thuốc.
- BR-08b: Ca **T3-Khẩn** do hệ thống xử lý ngay (hướng dẫn 115), không xếp hàng chờ. Không ai được hạ ca T3-Khẩn xuống tầng thấp hơn; người trực luôn được nâng tầng.
- BR-09: Agent **phải dùng lịch sử cuộc chat**: không hỏi lại thông tin khách đã cung cấp, nhất quán với câu trả lời trước, nhận ra câu hỏi nối tiếp. Lịch sử dài thì dùng bản tóm tắt cộng các tin gần nhất (xem 03, mục 1.3).

### 3.5 Quản lý (khung 3)

Quản lý làm việc qua một khung chat với **agent quản lý**. Các yêu cầu được hỗ trợ:

| Nhóm | Ví dụ yêu cầu | Kết quả |
|---|---|---|
| Tóm tắt | "Tóm tắt cuộc trò chuyện giữa người dùng A và người trực B hôm qua" | Form **Tóm tắt cuộc trò chuyện** |
| Hiệu suất | "Hiệu suất người trực B tuần này" | Form **Đánh giá hiệu suất người trực** |
| Chất lượng | "Đánh giá chất lượng tư vấn của cuộc chat #123" | Form **Đánh giá chất lượng tư vấn** |
| Báo cáo | "Báo cáo hôm nay" / "So sánh người trực B và C tháng 10" | Form **Báo cáo vận hành** / **So sánh người trực** |
| Tra cứu dữ liệu | "Những cuộc chat nào đang chờ quá 10 phút?", "Người dùng A đã hỏi gì trước đây?" | Trả lời dạng bảng hoặc danh sách, có liên kết mở cuộc chat |
| Phân quyền | "Nâng B lên C2 từ hôm nay", "Thu hồi quyền gửi nguyên gợi ý của C" | Agent **đề xuất thao tác**; quản lý bấm xác nhận trên thẻ xác nhận (D-6) |
| Chỉ định | "Giao cuộc chat #123 cho bác sĩ D" | Như trên |
| Tài liệu | "Chống chỉ định của paracetamol?" | Trả lời từ tài liệu, **có trích dẫn** (quản lý cần kiểm chứng) |

- BR-10: Agent quản lý chỉ truy cập dữ liệu qua **công cụ chỉ đọc** đã định nghĩa (xem 03, mục 6). Không tự sửa dữ liệu.
- BR-11: Số liệu trong báo cáo được **tính bằng code** từ dữ liệu sự kiện. Agent chỉ diễn giải, không tự ước lượng con số.
- BR-12: Agent quản lý cũng phải dùng lịch sử phiên làm việc. Ví dụ hỏi "còn người trực C thì sao?" thì áp dụng lại yêu cầu trước cho C.

## 4. Định nghĩa chỉ số hiệu suất người trực

Tính trên khoảng thời gian được chọn, theo giờ Việt Nam.

| Chỉ số | Cách tính |
|---|---|
| Số cuộc tiếp nhận | Số cuộc chat có sự kiện tiếp nhận/được chỉ định cho người đó |
| Tự tiếp nhận / được chỉ định | Tách theo loại sự kiện |
| Thời gian phản hồi đầu tiên (FRT) | Từ lúc được giao đến tin đầu tiên người trực gửi; báo cáo trung vị và p90 |
| Thời gian phản hồi trung bình | Trung bình khoảng cách từ tin khách đến tin trả lời kế tiếp của người trực |
| Thời gian xử lý | Từ lúc giao đến lúc đóng |
| Tỉ lệ dùng gợi ý AI | Số tin gửi nguyên / sửa / tự viết, chia cho tổng số tin |
| Mức độ sửa gợi ý | Độ khác biệt văn bản trung bình giữa gợi ý và tin gửi (0–100%) |
| Số lần chuyển / đẩy cấp | Đếm sự kiện |
| Cảnh báo vượt quyền | Số lần kiểm tra trước khi gửi phát hiện vượt quyền, và số lần người trực vẫn gửi sau khi xác nhận |
| Đánh giá của khách | Điểm trung bình 1–5 (nếu bật khảo sát cuối cuộc chat) và số lượt đánh giá |
| Tỉ lệ mở lại | Số cuộc chat bị mở lại trong 24 giờ, chia cho số cuộc đã đóng |
| Thời gian trực | Tổng thời gian ở trạng thái "đang trực" |

## 5. Trạng thái

**Cuộc trò chuyện:** `ai_active` (đang chat AI) → `waiting` (chờ người trực) → `assigned` (có người phụ trách) → `closed` (đã đóng), có thể mở lại thành `assigned` hoặc `waiting`. Thêm trạng thái `abandoned` khi khách rời đi lúc đang chờ quá 30 phút.

**Người trực:** `offline` · `online` (đang trực, nhận việc) · `busy` (đủ số cuộc tối đa) · `away` (tạm nghỉ, không nhận việc mới).
