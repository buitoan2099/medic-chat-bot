# Kịch bản hội thoại khách ↔ người trực

Cập nhật: 19/11/2026 · Dùng kèm [kich-ban-test-3-khung.md](kich-ban-test-3-khung.md)

Mỗi kịch bản là một cuộc chat nhiều lượt. Một người đóng vai **khách** (cửa sổ Home), một người đóng vai **người trực** (trang Người trực). Gõ đúng câu của khách; người trực **dùng gợi ý AI** hoặc gõ câu mẫu. Cột **Kiểm tra** là điều hệ thống phải làm ở lượt đó.

> Câu trả lời mẫu của người trực chỉ để **chạy thử luồng**, không phải nội dung tư vấn chuẩn. Nội dung tư vấn thật do Hội đồng chuyên môn duyệt.

Ký hiệu: 👤 khách · 🧑‍⚕️ người trực · 🔎 kiểm tra

---

## HT-1. Sốt thông thường: C2 tư vấn thuốc không kê đơn

Người trực: **Dược sĩ Lan (C2)**. Khách bắt đầu ở chế độ AI.

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | `Tôi bị sốt 38,5 độ từ hôm qua, nên uống thuốc gì?` | AI không trả lời thuốc, hiện thẻ vàng mời chuyển |
| 2 | 👤 | *(bấm 🧑‍⚕️ Chat với người trực)* | Khách thấy *Đang chờ người trực tiếp nhận… Xs* |
| 3 | 🧑‍⚕️ | *(tiếp nhận ở hàng chờ)* | Khách thấy *Dược sĩ Lan đã tiếp nhận…*; người trực thấy tin AI trước đó; cột gợi ý hiện ⏳ |
| 4 | 🧑‍⚕️ | `Chào bạn, mình là dược sĩ Lan. Bạn bao nhiêu tuổi, có đang mang thai, có dị ứng thuốc hay bệnh nền gì không?` | Gửi ngay; khách thấy tên *Dược sĩ Lan* |
| 5 | 👤 | `Tôi 30 tuổi, không mang thai, không dị ứng, không bệnh nền. Có hơi đau họng.` | *Hồ sơ ca* tự điền tuổi, triệu chứng (🤖); có gợi ý mới cho tin này |
| 6 | 🧑‍⚕️ | Dùng gợi ý, hoặc: `Bạn có thể dùng paracetamol 500 mg mỗi lần 1 viên, cách nhau ít nhất 4–6 giờ, không quá 4 g/ngày. Uống nhiều nước, nghỉ ngơi. Nếu sốt trên 39 độ, quá 3 ngày, khó thở hoặc đau họng nhiều, hãy đi khám.` | Gợi ý **trong phạm vi** C2 (không khung đỏ); gửi được |
| 7 | 👤 | `Cảm ơn, tôi uống được với nước cam không?` | Hiểu là hỏi tiếp, **không** có vạch đổi chủ đề |
| 8 | 🧑‍⚕️ | `Được bạn nhé, nước cam không ảnh hưởng đến paracetamol.` → **✅ Đóng** | Khách thấy thông báo kết thúc |
| 9 | 👤 | (vài phút sau) `Tôi uống rồi mà vẫn sốt 38 độ` | Cuộc chat **mở lại cho Lan** (trong 24 giờ) |

## HT-2. Người trực không đủ quyền: C1 gặp ca cần C2

Người trực: **Điều dưỡng An (C1)**. Quản lý chỉ định ca cho An (tick "giao dù chưa đủ cấp").

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | *(chọn Người trực ngay từ đầu)* `Tôi bị đau dạ dày, ợ chua mấy hôm nay, mua thuốc gì uống?` | Hàng chờ của An **không** có ca này (cần C2) |
| 2 | — | Quản lý: ⚡ Điều chỉnh → Chỉ định → Đang chờ → giao cho An, tick "giao dù chưa đủ cấp", lý do `test` | An thấy ca trong *Của tôi* |
| 3 | 🧑‍⚕️ | *(xem gợi ý)* | Gợi ý có **khung đỏ ⛔ vượt quyền → cần C2**; *Gửi luôn* và *Dùng & sửa* bị tắt |
| 4 | 🧑‍⚕️ | `Chào bạn, mình là điều dưỡng An. Bạn nên tránh đồ cay, rượu bia, cà phê, ăn đúng giờ. Mình sẽ chuyển bạn tới dược sĩ để tư vấn thuốc phù hợp nhé.` | Tự gõ: **gửi được** |
| 5 | 🧑‍⚕️ | **⬆️ Đẩy cấp** → C2, lý do `cần tư vấn thuốc` | Khách thấy *đang chuyển tới chuyên viên phù hợp hơn*; ca về hàng chờ C2 |
| 6 | 🧑‍⚕️ | **Dược sĩ Lan** tiếp nhận | Lan thấy toàn bộ tin của An và khách; gợi ý C2 cho câu đau dạ dày |
| 7 | 👤 | `Tôi có đang uống aspirin hằng ngày do bác sĩ kê` | Gợi ý lưu ý tương tác / nguy cơ dạ dày; hồ sơ ca có *thuốc đang dùng: aspirin* |
| 8 | 🧑‍⚕️ | `Vì bạn đang dùng aspirin lâu dài, bạn nên đi khám để bác sĩ đánh giá dạ dày và điều chỉnh thuốc, không tự mua thuốc thêm.` | Gửi được |

## HT-3. Thay người trực giữa chừng (quản lý)

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | `Con tôi 5 tuổi bị ho có đờm 1 tuần, sốt nhẹ về chiều` | Ca cần C2–C3 |
| 2 | 🧑‍⚕️ | Lan (C2) tiếp nhận: `Chào bạn, bé nặng bao nhiêu kg? Bé có thở nhanh, thở rít hay bỏ ăn không?` | |
| 3 | 👤 | `Bé 18kg, thở hơi nhanh, ăn kém` | Gợi ý có **dấu hiệu nặng** (thở nhanh ở trẻ) |
| 4 | — | Quản lý: ⚡ → Chỉ định → **Đang xử lý** → chọn ca này → giao cho **Bác sĩ Minh**, nâng cấp **C3**, lý do `trẻ thở nhanh` | Khách thấy *Bác sĩ Minh sẽ tiếp tục hỗ trợ bạn…*; Lan **không** gửi được nữa |
| 5 | 🧑‍⚕️ | Minh: `Chào bạn, bé ho kéo dài 1 tuần kèm thở nhanh cần được khám trực tiếp để nghe phổi. Bạn đưa bé đến cơ sở y tế trong hôm nay nhé. Nếu bé thở rút lõm ngực, tím môi hoặc li bì thì đi cấp cứu ngay.` | Gợi ý C3 có *cần hẹn khám trực tiếp* |
| 6 | — | Quản lý: `Tóm tắt cuộc chat <mã>` | F-1 ghi Lan → Minh, lý do, cần C3 |

## HT-4. Khách đổi sang bệnh khác giữa chừng

Người trực: **Lan (C2)**.

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | `Tôi bị cảm cúm, sổ mũi, hắt hơi 2 hôm` | |
| 2 | 🧑‍⚕️ | Trả lời theo gợi ý (cảm cúm) | Hồ sơ ca: triệu chứng chính = cảm cúm / sổ mũi |
| 3 | 👤 | `À tôi 35 tuổi, dị ứng penicilin nhé` | Hồ sơ ca thêm tuổi, dị ứng |
| 4 | 👤 | `Mà tôi bị nổi mẩn ngứa ở tay sau khi đi rừng thì bôi gì?` | Vạch **🆕 Khách chuyển sang hỏi vấn đề khác (trước đó: cảm cúm…)**; gợi ý chỉ về mẩn ngứa; hồ sơ **giữ** tuổi và dị ứng penicilin, **bỏ** cảm cúm |
| 5 | 👤 | `Còn uống thuốc gì không?` | **Không** đổi chủ đề; gợi ý hiểu là uống thuốc cho mẩn ngứa (ví dụ thuốc kháng histamin không kê đơn) |
| 6 | 🧑‍⚕️ | Nếu bước 4 không có vạch 🆕: bấm **🆕 Khách hỏi vấn đề mới** | Có vạch *do người trực đánh dấu*; gợi ý tạo lại |

## HT-5. Dấu hiệu cấp cứu xuất hiện giữa cuộc chat

Người trực: **Lan (C2)**.

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | `Tôi bị dị ứng nổi mề đay sau khi ăn hải sản` | Ca bình thường |
| 2 | 🧑‍⚕️ | `Bạn có thấy sưng môi, sưng mặt hay khó thở không?` | |
| 3 | 👤 | `Giờ thấy môi sưng lên và hơi khó thở` | Gợi ý có **dấu hiệu nặng** (phản vệ); ưu tiên khuyên đi cấp cứu |
| 4 | 🧑‍⚕️ | `Đây có thể là phản ứng dị ứng nặng. Bạn gọi 115 hoặc đến cơ sở y tế gần nhất NGAY, không tự lái xe.` | Gửi được |
| 5 | — | Quản lý: xem F-1 / F-6 | Có ghi chú dấu hiệu nặng |

> Ở **chế độ AI**, cùng câu ở bước 3 sẽ hiện **thẻ đỏ 115** ngay (quy tắc cấp cứu). Ở chế độ người trực, việc này do người trực xử lý, có gợi ý hỗ trợ.

## HT-6. Khách xin thuốc kê đơn

Người trực: **Bác sĩ Minh (C3)**.

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | `Tôi bị viêm họng mủ, bác sĩ kê cho tôi amoxicilin luôn được không?` | |
| 2 | 🧑‍⚕️ | *(xem gợi ý)* | Gợi ý **không kê đơn** kể cả với C3; khuyên khám trực tiếp |
| 3 | 🧑‍⚕️ | `Viêm họng có mủ cần được khám để quyết định có dùng kháng sinh hay không. Hệ thống không kê đơn trực tuyến, bạn vui lòng đến cơ sở y tế. Trong lúc chờ có thể súc họng nước muối, uống đủ nước.` | Gửi được |
| 4 | 👤 | `Thôi cho tôi liều amoxicilin là được, tôi tự mua` | |
| 5 | 🧑‍⚕️ | (Thử) tự gõ `Bạn uống amoxicilin 500mg ngày 3 lần trong 7 ngày` | **Rủi ro đã biết:** hiện vẫn **gửi được**, vì AI kiểm tra đang tắt và danh mục thuốc kê đơn còn rỗng. Ghi nhận, **không** gửi câu này cho khách thật |

## HT-7. Đối tượng đặc biệt: mang thai

Người trực: **Minh (C3)**.

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | (chế độ AI) `Tôi đang mang thai 5 tháng, bị đau đầu uống ibuprofen được không?` | AI mời chuyển (cần C3) |
| 2 | 👤 | *(chuyển người trực)* | Ca **không** hiện cho Lan (C2), chỉ Minh thấy |
| 3 | 🧑‍⚕️ | Minh xem gợi ý | Gợi ý lưu ý ibuprofen khi mang thai (theo tài liệu), khuyên trao đổi với bác sĩ sản |
| 4 | 🧑‍⚕️ | Trả lời theo gợi ý, hỏi thêm `Bạn đau đầu kèm mờ mắt, phù chân hay huyết áp cao không?` | Gửi được |
| 5 | 👤 | `Có, chân phù và nhìn hơi mờ` | Gợi ý có **dấu hiệu nặng** (nghi tiền sản giật), khuyên đi khám **ngay** |

## HT-8. Chuyển ca giữa hai người trực

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👤 | `Cho tôi hỏi thuốc nhỏ mắt cho mắt khô dùng loại nào?` | |
| 2 | 🧑‍⚕️ | Lan tiếp nhận, trả lời một câu | |
| 3 | 🧑‍⚕️ | Lan **↪️ Chuyển** cho Minh, ghi chú `em hết ca` | Minh thấy đề nghị trong *Của tôi*; Lan **vẫn** phụ trách đến khi Minh chấp nhận |
| 4 | 🧑‍⚕️ | Minh **Từ chối** | Lan vẫn phụ trách |
| 5 | 🧑‍⚕️ | Lan chuyển lại, Minh **Chấp nhận** | Minh phụ trách; Lan không gửi được |
| 6 | 🧑‍⚕️ | Minh đặt **⚫ Rời ca** khi còn ca | Bị nhắc phải chuyển, hoặc xác nhận trả về hàng chờ |

## HT-9. Không có ai trực

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 🧑‍⚕️ | Mọi người trực đặt **⚫ Rời ca** | |
| 2 | 👤 | (Người trực) `Tôi bị đau lưng sau khi mang vác nặng` | Khách thấy *Đang chờ người trực tiếp nhận…*, đồng hồ chạy |
| 3 | 👤 | `Có ai không ạ?` (gửi thêm khi chờ) | Tin được ghi, vẫn chờ |
| 4 | — | Chờ hơn 5 phút; quản lý bấm **Quá SLA** | Ca xuất hiện trong danh sách quá hạn |
| 5 | 🧑‍⚕️ | Lan bật **🟢 Đang trực** | Ca hiện trong hàng chờ của Lan, đủ 2 tin của khách; gợi ý cho tin mới nhất |

## HT-10. Quản lý theo dõi sau ca

Chạy sau các kịch bản trên.

| # | Ai | Nội dung | 🔎 Kiểm tra |
|---|---|---|---|
| 1 | 👔 | **Người trực… → Lan → 📝 F-6** | Đủ các ca Lan đã xử lý (HT-1, HT-2, HT-4, HT-5, HT-8…), câu trả lời trích đúng |
| 2 | 👔 | `Hôm nay Lan xử lý những gì? Có ca nào cần xem lại không?` | F-6 + nhận xét; nêu mã ca HT-5 (dị ứng nặng) hoặc HT-6 |
| 3 | 👔 | `So sánh An, Lan, Minh hôm nay` | F-5 |
| 4 | 👔 | `Đánh giá chất lượng cuộc chat <mã HT-3>` | F-3 có điểm và trích tin làm bằng chứng |

---

## Ghi kết quả

| Kịch bản | Lượt lỗi (#) | Mã cuộc chat | Ghi chú |
|---|---|---|---|
| HT-1 | | | |
| HT-2 | | | |
| … | | | |
