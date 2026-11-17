# Đặc tả: Hệ thống chat 3 khung (Người dùng · Người trực ban · Quản lý)

Phiên bản: 0.1 (bản nháp để review) · Ngày: 17/11/2026
Phạm vi: mở rộng chatbot tra cứu tài liệu hiện có (RAG trên Dược thư Quốc gia 2018) thành hệ thống tư vấn có người trực, AI hỗ trợ và quản lý.

## Mục lục

| File | Nội dung |
|---|---|
| [01-nghiep-vu.md](01-nghiep-vu.md) | Vai trò, cấp quyền chuyên môn, luồng nghiệp vụ, quy tắc nghiệp vụ |
| [02-giao-dien.md](02-giao-dien.md) | Khung 1/2/3, trang cấu hình model, trang phân quyền, popup điều chỉnh nhanh |
| [03-agents-va-prompt.md](03-agents-va-prompt.md) | Danh sách agent, prompt đầy đủ cho từng agent, form trả lời của quản lý |
| [04-du-lieu-va-luu-tru.md](04-du-lieu-va-luu-tru.md) | Mô hình dữ liệu, lưu trữ local theo ngày, lớp repository để chuyển sang DB |
| [05-kien-truc-va-phi-chuc-nang.md](05-kien-truc-va-phi-chuc-nang.md) | Kiến trúc, tích hợp với code hiện có, bảo mật, tuân thủ, hiệu năng |
| [06-nghiem-thu-va-lo-trinh.md](06-nghiem-thu-va-lo-trinh.md) | Tiêu chí nghiệm thu, lộ trình theo giai đoạn, câu hỏi mở |
| [07-xung-dot-kien-truc.md](07-xung-dot-kien-truc.md) | Xung đột giữa đặc tả và code hiện tại, các quyết định đã chốt |
| [08-technical-plan.md](08-technical-plan.md) | Kế hoạch kỹ thuật triển khai |
| [../phan-tang.md](../phan-tang.md) | Phân tầng ca bệnh, danh mục chuyên môn (chờ Hội đồng duyệt) |

## Tóm tắt

- **Khung 1 – Người dùng:** khi vào, chọn **chat với AI** (chỉ trả lời thông tin có trong tài liệu) hoặc **chat với người trực**. Ở chế độ AI, câu hỏi về chẩn đoán hay kê thuốc được trả lời bằng lời mời chuyển sang người trực.
- **Khung 2 – Người trực ban:**
  - nhận cuộc chat bằng cách tự tiếp nhận hoặc được quản lý chỉ định;
  - mỗi câu hỏi có **gợi ý trả lời từ agent ứng với cấp quyền** của người trực;
  - người trực gửi luôn hoặc sửa trước khi gửi; câu trả lời gửi khách **không kèm trích dẫn tài liệu**.
- **Khung 3 – Quản lý:** chat với agent quản lý để:
  - truy vấn dữ liệu (tóm tắt cuộc chat, hiệu suất người trực…) theo **form chuẩn**;
  - phân quyền cho người trực;
  - hỏi nội dung tài liệu.
  Có popup điều chỉnh nhanh ngay trong khung.
- **Ba cấp quyền chuyên môn** cho người trực, từ thấp đến cao, mỗi cấp có agent và prompt riêng:
  1. Tư vấn thông tin thuốc;
  2. Đánh giá & tư vấn thuốc **không kê đơn** cho bệnh nhẹ (tầng T2);
  3. Bác sĩ tư vấn ca nặng và hẹn khám trực tiếp (tầng T3-Chuyển; bác sĩ đã xác minh giấy phép).
- **Không kê đơn trực tuyến** ở bất kỳ cấp nào. Phân tầng ca bệnh và danh mục chuyên môn nằm trong [../phan-tang.md](../phan-tang.md).
- **Lưu trữ:**
  - lịch sử chat lưu local, chia theo ngày, mỗi cuộc trò chuyện một luồng;
  - dữ liệu đi qua lớp repository, nên sau này chuyển sang DB chỉ cần đổi cấu hình.
- **Trang cấu hình:** chọn model cho từng agent; cấu hình quyền cho người trực.

## Quyết định thiết kế chính (cần xác nhận)

| Mã | Quyết định đề xuất | Lý do |
|---|---|---|
| D-1 | **Backend FastAPI** giữ toàn bộ nghiệp vụ, dữ liệu, agent; **Streamlit nhiều trang** chỉ là client gọi API. Sau này có thể thay bằng web app riêng mà không đổi backend. | Ba khung cần trạng thái dùng chung, khoá tiếp nhận, cập nhật gần thời gian thực (quyết định Q-B, file 07). |
| D-2 | **Giữ Qdrant embedded**; backend là tiến trình **duy nhất** truy cập Qdrant (1 worker). Rebuild chỉ mục kiểu xanh–lục ở mức ứng dụng. | Không phát sinh hạ tầng mới (quyết định Q-A, file 07). |
| D-3 | Ba cấp quyền chuyên môn **lũy tiến**: cấp cao bao gồm cấp thấp. Từng quyền thao tác (tiếp nhận, chuyển tiếp…) cấu hình riêng. | Khớp với mô tả nghiệp vụ; đơn giản cho người cấu hình. |
| D-4 | Agent **chỉ gợi ý**. Mọi tin gửi khách ở chế độ người trực phải do người trực bấm gửi. | Trách nhiệm chuyên môn thuộc về con người. |
| D-5 | Ngày lưu trữ tính theo **giờ Việt Nam (Asia/Ho_Chi_Minh)**; mọi thời điểm lưu dạng UTC có múi giờ. | Báo cáo theo ngày làm việc, không lệch múi giờ. |
| D-6 | Agent quản lý **chỉ đọc**. Thao tác ghi (phân quyền, chỉ định) luôn phải qua bước xác nhận trên giao diện. | Tránh việc AI tự thay đổi quyền. |

## Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| Người dùng / khách | Người đặt câu hỏi ở khung 1 |
| Người trực (ban) | Nhân viên y tế trả lời khách ở khung 2 |
| Quản lý | Người giám sát, phân công, phân quyền ở khung 3 |
| Quản trị (admin) | Người cấu hình hệ thống: model, tài khoản |
| Cuộc trò chuyện | Một phiên hỏi đáp của một người dùng, có thể qua nhiều ngày |
| Agent | Một cấu hình AI (prompt + model + công cụ) cho một mục đích |
| Gợi ý (draft) | Câu trả lời agent soạn sẵn cho người trực |
| Tài liệu | Kho tài liệu đã lập chỉ mục RAG (hiện là Dược thư 2018) |
