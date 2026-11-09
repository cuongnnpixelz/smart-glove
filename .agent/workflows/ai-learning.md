---
description: Tự động trích xuất và lưu bài học/kinh nghiệm kỹ thuật vào .agent/learnings/
---

# AI Learning Workflow (AIoT Systems)

Sau khi giải quyết xong một vấn đề, sửa một lỗi khó hoặc tạo một kiến trúc mới, AI trích xuất các kinh nghiệm thực tế và lưu vào file tương ứng trong `.agent/learnings/` (ví dụ: `esp32-mqtt.md`, `tflite-micro.md`, `web-telemetry.md`,...).

---

## 1. Phân Loại Thông Tin Cần Lưu

Mỗi file learning được cấu trúc thành 4 phần rõ ràng:

1. **Architecture (Kiến trúc & Cấu hình phần cứng/mô hình)**:
   - Sơ đồ chân nối (Pinout), điện áp hoạt động.
   - Kích thước mô hình AI, cấu trúc tensor, tần số lấy mẫu.
2. **Bugs & Solutions (Lỗi đã gặp & Cách khắc phục)**:
   - Hiện tượng lỗi (ví dụ: ESP32 bị reset khi bật WiFi, cảm biến I2C treo khi mất dây GND, model dự đoán ra toàn 0).
   - Nguyên nhân gốc rễ (Root cause).
   - Cách xử lý triệt để (Hardware fix hoặc Code fix).
3. **How-To (Hướng dẫn từng bước đã thử nghiệm thành công)**:
   - Lệnh nạp firmware, lệnh build model, cấu hình broker MQTT.
4. **Patterns (Các đoạn mã mẫu chuẩn, tái sử dụng được)**:
   - Đoạn code mẫu non-blocking đọc cảm biến, code subscribe MQTT an toàn, hàm lượng tử hóa model,...

---

## 2. Quy Tắc Lưu Trữ
- Luôn lưu vào đường dẫn `.agent/learnings/`.
- Nếu chủ đề đã có file tồn tại, cập nhật thêm vào file đó thay vì tạo file trùng lặp.
- Đặt tên file theo định dạng `kebab-case` ngắn gọn (ví dụ: `esp32-freertos.md`, `yolov8-edge.md`, `chartjs-websocket.md`).