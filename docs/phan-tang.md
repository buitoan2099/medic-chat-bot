# Phân tầng ca bệnh và quy định kê đơn trực tuyến

> **Trạng thái: DỰ THẢO – chờ Hội đồng chuyên môn và Pháp chế duyệt danh mục, ngưỡng (mục 3, 4).**
> Đội kỹ thuật **không** đưa vào code bất kỳ danh mục hay ngưỡng nào trong tài liệu này trước khi có chữ ký duyệt.
>
> **Đã quyết định (17/11/2026):** hệ thống **không kê đơn trực tuyến** ở bất kỳ tầng hay cấp quyền nào (xem mục 5 và mục 7).
>
> Tài liệu liên quan: đặc tả kỹ thuật hệ thống chat 3 khung, [chat-3-khung/](chat-3-khung/README.md). Tài liệu này là câu trả lời cho câu hỏi mở **Q-1** ở [06-nghiem-thu-va-lo-trinh.md](chat-3-khung/06-nghiem-thu-va-lo-trinh.md).

## Mục lục

1. [Người duyệt](#1-người-duyệt)
2. [Hai khái niệm: tầng ca và cấp quyền người trực](#2-hai-khái-niệm-tầng-ca-và-cấp-quyền-người-trực)
3. [Danh mục bệnh nhẹ – tầng T2](#3-danh-mục-bệnh-nhẹ--tầng-t2)
4. [Tiêu chí ca nặng – tầng T3](#4-tiêu-chí-ca-nặng--tầng-t3)
5. [Thuốc: không kê đơn trực tuyến](#5-thuốc-không-kê-đơn-trực-tuyến)
6. [Ánh xạ sang đặc tả kỹ thuật](#6-ánh-xạ-sang-đặc-tả-kỹ-thuật)
7. [Quyết định và câu hỏi còn mở](#7-quyết-định-và-câu-hỏi-còn-mở)
8. [Phụ lục – Tham khảo nếu sau này làm kê đơn điện tử](#8-phụ-lục--tham-khảo-nếu-sau-này-làm-kê-đơn-điện-tử)

---

## 1. Người duyệt

| Phần | Người duyệt chính |
|---|---|
| Danh mục bệnh nhẹ T2 (mục 3) | Hội đồng chuyên môn |
| Tiêu chí ca nặng T3 (mục 4) | Hội đồng chuyên môn |
| Phạm vi tư vấn thuốc (mục 5) | Pháp chế + Hội đồng chuyên môn (Dược) |
| Ánh xạ kỹ thuật (mục 6) | Tech lead, **sau khi** 3 phần trên đã được duyệt |

Các căn cứ pháp lý được viết theo hiểu biết đến giữa năm 2026, **chưa tra cứu lại văn bản gốc**. Pháp chế cần đối chiếu số hiệu, hiệu lực và các văn bản sửa đổi mới nhất.

---

## 2. Hai khái niệm: tầng ca và cấp quyền người trực

Có hai trục khác nhau, không được lẫn:

- **Tầng ca (T1/T2/T3):** ca bệnh *nặng đến mức nào* và *được xử lý trực tuyến đến đâu*. Tài liệu này định nghĩa trục này.
- **Cấp quyền người trực (C1/C2/C3):** người trực *được làm gì*. Trục này được định nghĩa trong [01-nghiep-vu.md](chat-3-khung/01-nghiep-vu.md).

> Bản dự thảo trước dùng tên C1/C2/C3 cho tầng ca. Tên đã được đổi thành T1/T2/T3 để không trùng với cấp quyền người trực. Nội dung không đổi.

### 2.1 Tầng ca (giả định của tài liệu này)

| Tầng | Ý nghĩa | Kê đơn trực tuyến |
|---|---|---|
| **T1** | Sàng lọc, hướng dẫn tự chăm sóc, không có chẩn đoán | Không |
| **T2** | Bệnh nhẹ, xử lý từ xa: đánh giá sơ bộ, hướng dẫn chăm sóc tại nhà, tư vấn thuốc **không kê đơn**, hướng dẫn theo dõi | Không (chỉ tư vấn thuốc không kê đơn, mục 5) |
| **T3** | Ca nặng hoặc có dấu hiệu nguy hiểm, chuyển khám trực tiếp hoặc cấp cứu. Chia hai mức **T3-Khẩn** và **T3-Chuyển** (mục 4) | Không (chỉ hướng dẫn sơ cứu, chuyển tuyến) |

**Nguyên tắc an toàn:** khi không chắc thì **nâng tầng** (T2 lên T3), không bao giờ hạ tầng tự động.

### 2.2 Ánh xạ tầng ca ↔ cấp quyền người trực (đã chốt theo H-1, H-2, H-3)

| Tầng ca | Ai được xử lý | Được làm gì | Không được |
|---|---|---|---|
| Hỏi thông tin thuốc/bệnh chung (chưa thành "ca") | AI (chế độ AI) hoặc người trực C1 trở lên | Cung cấp thông tin theo tài liệu | Áp dụng cho trường hợp cụ thể |
| **T1** | Người trực **C1** trở lên | Sàng lọc, hướng dẫn tự chăm sóc, khuyên đi khám | Chẩn đoán; gợi ý thuốc cho trường hợp cụ thể |
| **T2** | Người trực **C2** trở lên | Đánh giá sơ bộ, hướng dẫn chăm sóc tại nhà, tư vấn thuốc **không kê đơn** theo mục 5, **bắt buộc** hướng dẫn theo dõi và dấu hiệu phải đi khám | Thuốc kê đơn (mọi cấp, kể cả bác sĩ). Ca cần thuốc kê đơn thì chuyển **T3-Chuyển** để hẹn khám trực tiếp. |
| **T3-Chuyển** | Bác sĩ (**C3**) | Tư vấn, giải thích tình trạng và lý do cần khám, hướng dẫn chăm sóc/sơ cứu trong lúc chờ, **hẹn khám trực tiếp trong 24 giờ** | Kê đơn trực tuyến; đưa phác đồ điều trị để người bệnh tự áp dụng |
| **T3-Khẩn** | Hệ thống xử lý ngay, không chờ người trực | Dừng phiên, hiển thị hướng dẫn gọi 115 / đến cơ sở cấp cứu | Xếp hàng chờ tư vấn |

---

## 3. Danh mục bệnh nhẹ – tầng T2

Một ca chỉ ở T2 khi **cả hai** điều kiện đều đúng:
1. Tình trạng thuộc danh mục dưới đây.
2. Không có tiêu chí nào ở mục 4 (Ca nặng T3).

Danh mục cần được đối chiếu với danh mục bệnh được khám chữa bệnh từ xa do Bộ Y tế ban hành (Thông tư 30/2023/TT-BYT, **cần xác minh**). Danh mục nội bộ **không được rộng hơn** danh mục của Bộ Y tế.

| Nhóm | Tình trạng | Điều kiện để ở T2 | Chuyển T3 khi |
|---|---|---|---|
| Hô hấp | Cảm lạnh, viêm mũi họng cấp | Sốt < 39°C, dưới 5 ngày, ăn uống được | Khó thở, SpO2 < 94%, sốt ≥ 3 ngày ở trẻ < 2 tuổi |
| Hô hấp | Ho cấp không biến chứng | Dưới 3 tuần, không ho ra máu | Ho ra máu, đau ngực, khò khè mới |
| Hô hấp | Viêm mũi dị ứng | Đã từng được chẩn đoán | Phù mặt, môi; khó thở |
| Tiêu hóa | Tiêu chảy cấp nhẹ | Dưới 3 ngày, uống được, không máu trong phân | Dấu hiệu mất nước, phân máu, nôn tất cả mọi thứ |
| Tiêu hóa | Trào ngược, khó tiêu | Không sụt cân, không nuốt nghẹn, < 50 tuổi | Nôn ra máu, phân đen, đau bụng dữ dội |
| Tiêu hóa | Táo bón cấp | Không đau bụng nhiều | Chướng bụng, không trung tiện |
| Da liễu | Mụn trứng cá nhẹ–vừa, viêm da tiếp xúc, mề đay cấp, nấm da | Có ảnh rõ nét, tổn thương khu trú | Lan nhanh, bọng nước diện rộng, kèm sốt hoặc phù môi |
| Mắt | Viêm kết mạc | Không giảm thị lực, không đau nhức | Giảm thị lực, chấn thương mắt, đeo kính áp tròng |
| Tiết niệu | Viêm bàng quang không biến chứng ở nữ 18–65 tuổi | Không mang thai, không sốt, không đau hông lưng | Sốt, đau hông lưng, tái phát ≥ 3 lần/năm |
| Cơ xương khớp | Đau lưng cấp, căng cơ | Không chấn thương, không tê yếu chân | Rối loạn đại tiểu tiện, yếu chi, sau ngã |
| Thần kinh | Đau đầu kiểu căng thẳng | Giống các cơn trước | Đau đầu dữ dội đột ngột, kèm sốt cứng gáy, yếu liệt |
| Bệnh mạn tính ổn định | Tư vấn theo dõi tăng huyết áp, đái tháo đường típ 2, rối loạn mỡ máu (không tái kê đơn) | Đã khám trực tiếp và đang điều trị ổn định; có số đo gần đây | HA ≥ 180/110, đường huyết < 70 hoặc > 300 mg/dL, triệu chứng mới; cần chỉnh/tái kê đơn → hẹn khám trực tiếp |

### 3.1 Loại khỏi T2 bất kể bệnh gì (đề xuất, Hội đồng chốt)

- Trẻ dưới 3 tháng tuổi.
- Phụ nữ mang thai hoặc sau sinh dưới 6 tuần, trừ khi có bác sĩ sản tham gia.
- Lần đầu khám một bệnh mạn tính (chưa có chẩn đoán trực tiếp).
- Người bệnh không tự mô tả được triệu chứng và không có người đi cùng.
- Ca tái khám lần thứ 2 cho cùng triệu chứng trong 7 ngày mà không đỡ.
- **Người trên 75 tuổi, hoặc có nhiều bệnh nền** (đã chốt H-5): mặc định vào **T3-Chuyển**. Định nghĩa "nhiều bệnh nền" đề xuất: ≥ 2 bệnh mạn tính đang điều trị, hoặc có suy gan, suy thận, suy tim, hoặc đang dùng ≥ 5 thuốc. Hội đồng chốt định nghĩa.

> Các ngưỡng số (39°C, SpO2 94%, HA 180/110…) là giá trị thường gặp trong hướng dẫn lâm sàng. Chúng được đặt ở đây để Hội đồng sửa, **chưa phải ngưỡng đã duyệt**.

---

## 4. Tiêu chí ca nặng – tầng T3

Chỉ cần **một** tiêu chí dưới đây là ca vào T3. T3 chia hai mức để hệ thống xử lý khác nhau:

| Mức | Xử lý |
|---|---|
| **T3-Khẩn** | Dừng phiên, hiển thị ngay hướng dẫn gọi 115 hoặc đến cơ sở cấp cứu gần nhất, không xếp hàng chờ bác sĩ |
| **T3-Chuyển** | Bác sĩ tư vấn và hẹn khám trực tiếp trong 24 giờ, không kê đơn trực tuyến, không đưa phác đồ để người bệnh tự áp dụng |

| Nhóm | Tiêu chí (đề xuất) | Mức |
|---|---|---|
| Tim mạch | Đau tức ngực, đặc biệt lan tay trái, hàm; vã mồ hôi | T3-Khẩn |
| Thần kinh | Méo miệng, yếu liệt một bên, nói khó đột ngột; co giật; lơ mơ, lú lẫn | T3-Khẩn |
| Hô hấp | Khó thở lúc nghỉ, nói không trọn câu, tím môi, SpO2 < 92% | T3-Khẩn |
| Dị ứng | Phù môi, lưỡi, họng; khó thở sau tiếp xúc thuốc, thức ăn, côn trùng | T3-Khẩn |
| Chảy máu | Nôn ra máu, đi ngoài phân đen, chảy máu không cầm | T3-Khẩn |
| Chấn thương | Chấn thương đầu có nôn hoặc mất ý thức; nghi gãy xương; bỏng rộng | T3-Khẩn |
| Nhi | Trẻ < 3 tháng sốt ≥ 38°C; li bì, bỏ bú; co rút lồng ngực; thóp lõm | T3-Khẩn |
| Sản | Mang thai có ra huyết, đau bụng, đau đầu nhiều, nhìn mờ | T3-Khẩn |
| Tâm thần | Có ý định làm hại bản thân hoặc người khác | T3-Khẩn, kèm số đường dây hỗ trợ |
| Nhiễm trùng | Sốt ≥ 39°C kéo dài ≥ 3 ngày; sốt kèm cứng gáy hoặc ban xuất huyết | T3-Khẩn nếu cứng gáy/ban; còn lại T3-Chuyển |
| Tiêu hóa | Đau bụng dữ dội hoặc khu trú hố chậu phải; dấu hiệu mất nước | T3-Khẩn |
| Chỉ số sinh tồn tự đo | HA ≥ 180/110 kèm triệu chứng; mạch > 120 hoặc < 50 lúc nghỉ; đường huyết < 70 mg/dL | T3-Khẩn |
| Diễn tiến | Triệu chứng nặng lên sau điều trị T2, hoặc cần xét nghiệm, chẩn đoán hình ảnh, khám thực thể để chẩn đoán | T3-Chuyển |
| Đối tượng nguy cơ | Người > 75 tuổi; người có nhiều bệnh nền (định nghĩa ở mục 3.1) | T3-Chuyển (mặc định, H-5) |
| Hết thời gian tự điều trị | Đã dùng thuốc không kê đơn quá thời gian tối đa (mục 5.2) mà không đỡ | T3-Chuyển |
| Phán đoán bác sĩ | Bác sĩ không đủ cơ sở chẩn đoán qua khám từ xa | T3-Chuyển |

- Bác sĩ **luôn có quyền** nâng một ca T2 lên T3 bằng phán đoán lâm sàng.
- Hệ thống **không cho phép** hạ một ca T3-Khẩn xuống T2.

---

## 5. Thuốc: không kê đơn trực tuyến

**Quyết định:** hệ thống **không kê đơn trực tuyến**, không phát hành đơn thuốc ở bất kỳ tầng ca hay cấp quyền nào, kể cả bác sĩ.

| Nhóm thuốc | Trong chat | Ai |
|---|---|---|
| Thuốc không kê đơn (OTC) | Được tư vấn cho ca T2: tên hoạt chất, cách dùng, liều theo tài liệu, thời gian dùng tối đa trước khi phải đi khám. Ghi vào hồ sơ ca. | Người trực C2 trở lên |
| Thông tin chung về thuốc kê đơn (công dụng, tác dụng phụ, tương tác…) | Được giải thích như thông tin tham khảo, **không** khuyên dùng cho trường hợp cụ thể | Mọi cấp, AI |
| Thuốc kê đơn cho trường hợp cụ thể | **Không.** Ca cần thuốc kê đơn → T3-Chuyển, bác sĩ tư vấn và hẹn khám trực tiếp | — |
| Người bệnh hỏi về thuốc kê đơn đang dùng (do bác sĩ điều trị kê) | Được giải thích cách dùng theo đơn sẵn có, tác dụng phụ, dấu hiệu cần báo bác sĩ; **không** khuyên tự đổi liều, ngừng thuốc | Mọi cấp |

Ngoại lệ trong nhóm OTC (đề xuất, Hội đồng Dược chốt): không tư vấn OTC cho các đối tượng đã bị loại khỏi T2 (mục 3.1), trừ hướng dẫn chung và khuyên đi khám.

### 5.1 Đề xuất cách xây dựng danh sách thuốc không kê đơn theo tình trạng (H-7)

> **Đề xuất – chờ Hội đồng Dược duyệt.** Mục này mô tả *cách làm* và *khung dữ liệu*; danh sách thuốc chính thức do Hội đồng Dược soạn.

**Nguyên tắc:**
1. **Danh sách trắng:** người trực C2 và agent AG-3 chỉ được tư vấn thuốc **có trong danh sách của đúng tình trạng đó**. Thuốc ngoài danh sách thì không tư vấn, hoặc chuyển C3.
2. **Nguồn:** danh sách = giao của ba tập:
   - danh mục thuốc không kê đơn chính thức của Bộ Y tế (Thông tư 07/2017/TT-BYT, **cần Pháp chế xác minh** văn bản hiện hành);
   - thuốc có chuyên luận trong Dược thư 2018;
   - thuốc phù hợp với tình trạng, theo Hội đồng Dược.
3. **Không chép liều vào danh sách:** danh sách chỉ ghi hoạt chất, đối tượng và giới hạn. **Liều lấy từ Dược thư** (agent tra RAG, kèm trang để người trực kiểm chứng). Như vậy không có hai nguồn liều mâu thuẫn nhau.
4. **Thời gian dùng tối đa** trước khi phải đi khám là **bắt buộc** cho mỗi dòng. Quá thời gian mà không đỡ thì ca chuyển T3-Chuyển (bảng tiêu chí mục 4).
5. **Phải hỏi đủ trước khi tư vấn:** tuổi, cân nặng (trẻ em), dị ứng, thuốc đang dùng, bệnh nền liên quan (gan, thận, dạ dày, hen…). Thiếu thông tin thì hỏi, chưa tư vấn thuốc.

**Khung dữ liệu cho mỗi dòng** (lưu trong bộ quy tắc có phiên bản, mục 6):

| Trường | Ví dụ ý nghĩa |
|---|---|
| Tình trạng T2 | Cảm lạnh, viêm mũi họng cấp |
| Mục tiêu | Hạ sốt, giảm đau |
| Hoạt chất | Tên hoạt chất (không ghi biệt dược) |
| Đối tượng | Người lớn / trẻ từ X tuổi (hoặc từ Y kg) |
| Không dùng khi | Các chống chỉ định phải hỏi trước (vd bệnh gan, dị ứng…) |
| Thời gian tối đa | Số ngày dùng tối đa trước khi phải đi khám |
| Tham chiếu liều | Chuyên luận Dược thư (tên + trang) |
| Ghi chú tư vấn | Lưu ý bắt buộc nói với khách |

**Rà soát danh mục T2 khi không kê đơn** (đề xuất ban đầu, Hội đồng chốt):

| Tình trạng T2 | Xử lý được bằng thuốc không kê đơn? | Đề xuất |
|---|---|---|
| Cảm lạnh, viêm mũi họng cấp | Có (hạ sốt/giảm đau, chăm sóc tại nhà) | Giữ T2 |
| Ho cấp không biến chứng | Hạn chế (chủ yếu chăm sóc tại nhà) | Giữ T2; thuốc ho cho trẻ em do Hội đồng quyết |
| Viêm mũi dị ứng | Có (kháng histamin không kê đơn) | Giữ T2 |
| Tiêu chảy cấp nhẹ | Có (bù nước – điện giải) | Giữ T2 |
| Trào ngược, khó tiêu | Có (thuốc kháng acid) | Giữ T2 |
| Táo bón cấp | Có (thuốc nhuận tràng không kê đơn) | Giữ T2 |
| Nấm da; mề đay cấp | Có (kháng nấm bôi; kháng histamin) | Giữ T2 |
| Viêm da tiếp xúc | Hạn chế | Giữ T2 nếu Hội đồng có thuốc bôi phù hợp trong danh mục không kê đơn |
| Mụn trứng cá nhẹ–vừa | Hạn chế: mức vừa thường cần thuốc kê đơn | Thu hẹp còn **mụn nhẹ**; mức vừa → T3-Chuyển |
| Viêm kết mạc | Hạn chế: nghi nhiễm khuẩn cần thuốc kê đơn | Chỉ chăm sóc, vệ sinh; nghi nhiễm khuẩn → T3-Chuyển |
| Viêm bàng quang không biến chứng | **Không** (cần kháng sinh) | **Bỏ khỏi T2 → T3-Chuyển** |
| Đau lưng cấp, căng cơ | Có (giảm đau không kê đơn) | Giữ T2 |
| Đau đầu kiểu căng thẳng | Có (giảm đau không kê đơn) | Giữ T2 |
| Bệnh mạn tính ổn định | Không áp dụng (không tư vấn thuốc mới, không tái kê đơn) | Chỉ tư vấn theo dõi; cần chỉnh thuốc → T3-Chuyển |

**Thời gian tối đa mặc định** (giá trị gợi ý thường gặp trên hướng dẫn sử dụng thuốc không kê đơn, **chưa duyệt**, đặt ở đây để Hội đồng sửa):

| Mục tiêu | Tối đa trước khi phải đi khám |
|---|---|
| Hạ sốt | 3 ngày |
| Giảm đau | 5 ngày |
| Tiêu chảy | 2 ngày dùng bù nước mà không đỡ, hoặc theo ngưỡng T2 (< 3 ngày) |
| Táo bón | 7 ngày |
| Khó tiêu, trào ngược | 14 ngày |
| Dị ứng, mề đay | 7 ngày |
| Nấm da | 14 ngày không cải thiện |

**Quy trình:**
1. Dược sĩ lâm sàng soạn bản nháp theo khung trên.
2. Hội đồng Dược duyệt và ký.
3. Kỹ thuật nạp thành bộ quy tắc có phiên bản.
4. Chạy bộ câu hỏi kiểm thử (AC-5.2) trước khi bật.
5. Rà soát lại mỗi 6 tháng, hoặc khi có văn bản pháp lý hay tài liệu mới.

**Hệ thống dùng danh sách thế nào:**
- AG-3 chỉ gợi ý thuốc trong danh sách của tình trạng, kèm thời gian tối đa.
- Kiểm tra trước khi gửi (AG-6) cảnh báo khi:
  - thuốc không nằm trong danh sách của tình trạng;
  - thiếu thời gian tối đa hay hướng dẫn theo dõi;
  - khách thuộc đối tượng "không dùng khi".

### 5.2 Căn cứ pháp lý cần Pháp chế xác minh (khám chữa bệnh từ xa, tư vấn thuốc, dữ liệu)

Danh sách viết theo hiểu biết, **chưa tra văn bản gốc**. Số hiệu, hiệu lực và văn bản thay thế đều cần kiểm tra.

| Văn bản | Nội dung liên quan | Cần kiểm tra |
|---|---|---|
| Luật Khám bệnh, chữa bệnh số 15/2023/QH15 | Khám bệnh, chữa bệnh từ xa; giấy phép hành nghề; hồ sơ bệnh án điện tử | Điều khoản cụ thể về khám từ xa |
| Nghị định 96/2023/NĐ-CP | Hướng dẫn Luật KBCB | Văn bản sửa đổi sau 2023 |
| Thông tư 30/2023/TT-BYT | Danh mục bệnh, tình trạng bệnh được khám chữa bệnh từ xa | Đối chiếu từng dòng với danh mục T2 |
| Thông tư 52/2017/TT-BYT và các thông tư sửa đổi (18/2018, 04/2022) | Kê đơn thuốc ngoại trú, đơn thuốc điện tử | Có thể đã được thay thế bởi thông tư mới năm 2025 |
| Luật Dược 2016, sửa đổi 2024 | Thuốc kê đơn, thuốc kiểm soát đặc biệt, bán thuốc trực tuyến | Quy định về kinh doanh thuốc qua thương mại điện tử |
| Thông tư 07/2017/TT-BYT | Danh mục thuốc không kê đơn | Văn bản hiện hành, đối chiếu danh sách mục 5.1 |
| Luật Giao dịch điện tử 2023 | Giá trị pháp lý của chữ ký số trên đơn | Chỉ liên quan nếu sau này làm kê đơn điện tử (phụ lục mục 8) |
| Nghị định 13/2023/NĐ-CP và Luật Bảo vệ dữ liệu cá nhân 2025 | Dữ liệu sức khỏe là dữ liệu nhạy cảm: đồng ý, lưu trữ, chia sẻ | Nghĩa vụ đánh giá tác động xử lý dữ liệu |

---

## 6. Ánh xạ sang đặc tả kỹ thuật

**Nguyên tắc:** nội dung chuyên môn nằm trong **cấu hình có phiên bản và có người duyệt**, không viết cứng trong code. Nhờ vậy Hội đồng sửa được danh mục mà không cần triển khai lại.

| Yêu cầu | Cách làm đề xuất | Liên quan trong đặc tả |
|---|---|---|
| Danh mục T2, tiêu chí T3, danh sách thuốc không kê đơn theo tình trạng (5.1) | Bộ quy tắc (rule set) dạng dữ liệu; mỗi bản có `version`, `approved_by`, `approved_at`, `effective_from` | Lưu cùng cấu hình agent, [04](chat-3-khung/04-du-lieu-va-luu-tru.md) mục 3 |
| Thứ tự đánh giá | Kiểm tra T3-Khẩn trước, rồi loại trừ chung (3.1), rồi T2; không khớp gì thì về T3-Chuyển | Agent phân loại AG-0, [03](chat-3-khung/03-agents-va-prompt.md) mục 2 |
| T3-Khẩn | Chặn luồng xếp hàng, hiển thị màn hình cấp cứu + nút gọi 115 | UI-1.4, [02](chat-3-khung/02-giao-dien.md) |
| Nâng tầng | Bác sĩ nâng T2 → T3 bất cứ lúc nào; không có thao tác hạ từ T3-Khẩn | Sự kiện "đẩy cấp", [01](chat-3-khung/01-nghiep-vu.md) BR-04 |
| Không kê đơn | Không có chức năng kê đơn. Kiểm tra trước khi gửi **chặn** tin gợi ý thuốc kê đơn cho trường hợp cụ thể ở **mọi cấp**; danh mục thuốc kê đơn lấy từ danh mục chính thức (Q-2 của đặc tả) | Kiểm tra trước khi gửi AG-6, [03](chat-3-khung/03-agents-va-prompt.md) mục 6 |
| Kiểm tra an toàn thuốc OTC | Chặn cứng khi gợi ý thuốc mà người bệnh đã ghi nhận dị ứng; cảnh báo tương tác, người trực phải ghi lý do nếu bỏ qua | Kiểm tra trước khi gửi AG-6 |
| Truy vết | Audit log: tầng được xếp, phiên bản rule set áp dụng, ai thay đổi tầng và lý do | `AuditLog`, `ConversationEvent`, [04](chat-3-khung/04-du-lieu-va-luu-tru.md) |
| Phát hành | Feature flag theo rule set; chỉ bật production khi rule set đã có chữ ký duyệt | Lộ trình giai đoạn 0, [06](chat-3-khung/06-nghiem-thu-va-lo-trinh.md) |

---

## 7. Quyết định và câu hỏi còn mở

### 7.1 Đã quyết định (17/11/2026)

| Mã | Câu hỏi | Quyết định |
|---|---|---|
| H-1 | Cấp quyền C2 (dược sĩ, y sĩ…) được làm gì với ca T2? | Theo tài liệu này: chỉ bác sĩ được kê đơn. Kết hợp với H-3 (không kê đơn trực tuyến): **C2 chỉ tư vấn thuốc không kê đơn** kèm hướng dẫn theo dõi. |
| H-2 | Bác sĩ C3 với ca T3-Chuyển được làm gì? | Theo tài liệu này: **tư vấn và hẹn khám trực tiếp trong 24 giờ, không kê đơn**, không đưa phác đồ để người bệnh tự áp dụng. |
| H-3 | Có làm kê đơn điện tử không? | **Không.** Hệ thống không kê đơn trực tuyến. Yêu cầu kê đơn điện tử chuyển xuống phụ lục mục 8 để tham khảo nếu sau này làm dự án riêng. |
| H-5 | Người > 75 tuổi hoặc nhiều bệnh nền có mặc định vào T3-Chuyển? | **Có.** Đã thêm vào nhóm loại trừ (3.1) và tiêu chí T3 (mục 4). Định nghĩa "nhiều bệnh nền" còn chờ chốt (H-8). |

### 7.2 Còn mở – Hội đồng chốt

| Mã | Câu hỏi |
|---|---|
| H-7 | Danh sách thuốc không kê đơn theo từng tình trạng T2 và thời gian dùng tối đa. Đã có **đề xuất cách làm** ở mục 5.1; cần Hội đồng Dược soạn danh sách chính thức, duyệt bảng rà soát T2 (đặc biệt: bỏ viêm bàng quang khỏi T2, thu hẹp mụn trứng cá còn mức nhẹ) và thời gian tối đa. |
| H-8 | Định nghĩa "nhiều bệnh nền" cho H-5. Đề xuất: ≥ 2 bệnh mạn tính đang điều trị, hoặc suy gan/thận/tim, hoặc đang dùng ≥ 5 thuốc. |

> H-4 (kháng sinh) và H-6 (corticoid toàn thân) không còn cần quyết định vì không kê đơn trực tuyến; giữ trong phụ lục.

---

## 8. Phụ lục – Tham khảo nếu sau này làm kê đơn điện tử

> **Không áp dụng.** Nội dung dưới đây là đề xuất ban đầu, giữ lại để tham khảo nếu đơn vị triển khai kê đơn điện tử thành dự án riêng (cần duyệt lại toàn bộ).

Đề xuất ban đầu: chỉ ca T2 được kê đơn, chỉ bác sĩ có giấy phép hành nghề còn hiệu lực được kê, mọi đơn là đơn thuốc điện tử có chữ ký số, liên thông hệ thống đơn thuốc quốc gia.

### 8.1 Phạm vi thuốc (đề xuất ban đầu)

| Nhóm thuốc | Kê trực tuyến | Ghi chú |
|---|---|---|
| Thuốc không kê đơn (OTC) | Được tư vấn | Không cần đơn nhưng ghi vào hồ sơ |
| Thuốc kê đơn thông thường cho bệnh T2 | Được | Theo phác đồ nội bộ đã duyệt cho từng bệnh |
| Thuốc duy trì bệnh mạn tính ổn định | Được, có điều kiện | Chỉ tái kê đơn đã có từ lần khám trực tiếp; tối đa số ngày theo quy định kê đơn mạn tính |
| Kháng sinh | Câu hỏi mở (H-4) | Đề xuất chỉ cho chẩn đoán cụ thể (ví dụ viêm bàng quang không biến chứng), không cho cảm lạnh |
| Corticoid đường toàn thân | Không | Trừ tái kê đơn đang dùng, Hội đồng quyết |
| Thuốc gây nghiện, hướng thần, tiền chất | Không | Thuốc kiểm soát đặc biệt |
| Thuốc độc tế bào, thuốc cần theo dõi xét nghiệm | Không | |
| Thuốc cho phụ nữ mang thai, trẻ < 3 tháng | Không | Đã loại khỏi T2 |

### 8.2 Yêu cầu với mỗi đơn (đề xuất ban đầu)

- Bác sĩ đã xác thực, giấy phép hành nghề còn hiệu lực và đúng phạm vi chuyên môn.
- Người bệnh đã định danh (họ tên, ngày sinh, số định danh cá nhân, hoặc thông tin người giám hộ với trẻ em).
- Chẩn đoán có mã ICD-10 nằm trong danh mục T2.
- Đã kiểm tra dị ứng thuốc, tương tác với thuốc đang dùng, mang thai/cho con bú.
- Thuốc ghi theo tên hoạt chất, hàm lượng, liều, số ngày dùng.
- Ký số, sinh mã đơn và liên thông hệ thống đơn thuốc quốc gia.
- Người bệnh nhận đơn kèm hướng dẫn dùng thuốc và dấu hiệu cần quay lại hoặc đi khám ngay.
- Lưu toàn bộ phiên khám (ghi chép, ảnh, đơn) theo thời hạn lưu trữ hồ sơ bệnh án.
