---
description: Quy trình lập kế hoạch và triển khai dự án IoT, Hệ thống nhúng, Deep Learning và Web Application
---

# AIoT Project Execution Workflow

Quy trình 3 pha chuẩn: **Khảo Sát & Thiết Kế Kiến Trúc → Thực Thi Code Chi Tiết → Đúc Kết Kinh Nghiệm (Save Learnings)**.

---

## Pha 1: KHẢO SÁT & THIẾT KẾ KIẾN TRÚC

Trước khi viết bất kỳ dòng mã nào, AI cần làm rõ và thống nhất kiến trúc:

### Bước 1.1: Load Learnings liên quan
1. Quét danh sách file trong `.agent/learnings/`.
2. Đọc các bài học hoặc kinh nghiệm đã có về phần cứng, mô hình AI hoặc giao diện tương tự.
3. Thông báo ngắn gọn những gì đã nạp được.

### Bước 1.2: Xác định 4 tầng kỹ thuật (System Mapping)
- **Tầng Thiết bị (Firmware)**: Xác định chip, pinout, cách đọc cảm biến, chu kỳ gửi dữ liệu.
- **Tầng AI / Xử lý dữ liệu**: Kiến trúc mô hình, vị trí inference (Edge hay Server), input/output tensor.
- **Tầng Giao thức / Mạng**: Địa chỉ broker MQTT, topic định danh, cấu trúc JSON payload.
- **Tầng Web / Người dùng**: Bố cục dashboard, các nút điều khiển và biểu đồ cần hiển thị.

---

## Pha 2: THỰC THI (EXECUTION)

### Bước 2.1: Tạo danh sách công việc (Task Checklist)
Chia nhỏ công việc theo từng phần độc lập để dễ kiểm thử:
- [ ] Thiết kế sơ đồ nối dây & Cấu hình chân (Wiring & Pinout).
- [ ] Viết mã nguồn Firmware nhúng (kèm xử lý ngắt, reconnect WiFi/MQTT, non-blocking loop).
- [ ] Xây dựng hoặc chuyển đổi mô hình Deep Learning (huấn luyện, convert TFLite/ONNX, lượng tử hóa INT8).
- [ ] Viết backend / cầu nối dữ liệu (FastAPI / Node.js WebSocket hoặc MQTT bridge nếu cần).
- [ ] Viết giao diện Web Dashboard hiển thị dữ liệu và bảng điều khiển.

### Bước 2.2: Triển khai mã nguồn
- Viết code hoàn chỉnh, có giải thích ngắn gọn các hằng số cấu hình (WiFi SSID, MQTT broker IP, Baudrate, GPIO pins).
- Tuân thủ nghiêm ngặt các nguyên tắc an toàn bộ nhớ và tối ưu tài nguyên đã định trong `rules/`.

### Bước 2.3: Kiểm tra và xác minh (Verification)
- Kiểm tra tính tương thích dữ liệu giữa Firmware và Web (format JSON có khớp key không).
- Đánh giá thời gian đáp ứng và độ ổn định của hệ thống.

---

## Pha 3: LƯU TRỮ KINH NGHIỆM (SAVE LEARNINGS)
- Ghi lại các lỗi phần cứng, cấu hình pinout hoặc thủ thuật tối ưu vừa phát hiện vào `.agent/learnings/` để tái sử dụng ở các phiên làm việc tiếp theo.
