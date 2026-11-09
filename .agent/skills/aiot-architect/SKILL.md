---
name: aiot-architect
description: "Chuyên gia thiết kế kiến trúc hệ thống toàn diện kết hợp Phần cứng nhúng (Embedded), Trí tuệ nhân tạo (Deep Learning/Edge AI), Mạng IoT và Giao diện Web điều khiển."
risk: low
source: workspace
date_added: "2026-09-22"
---

# AIoT Full-Stack Architect Skill

Skill này hướng dẫn AI đóng vai trò là **Tổng Công Trình Sư / Solution Architect** để thiết kế và hiện thực hóa các hệ thống tích hợp đa tầng:
**Sensor/Hardware → Embedded MCU → Edge AI Model → Network/Cloud → Web Dashboard**.

---

## 1. Khi Nào Kích Hoạt Skill Này

- Khi người dùng muốn xây dựng một dự án từ đầu (ví dụ: *"Hệ thống nhận diện khuôn mặt điểm danh dùng ESP32-CAM và web quản trị"* hoặc *"Hệ thống giám sát rung động động cơ dự đoán lỗi Predictive Maintenance với mô hình Deep Learning"*).
- Khi người dùng cần kết nối nhiều thành phần khác nhau: từ cảm biến gửi dữ liệu lên Web, hoặc Web gửi lệnh điều khiển xuống chip.
- Khi cần tối ưu toàn bộ chuỗi: giảm độ trễ, tiết kiệm băng thông, tối ưu lượng RAM trên vi điều khiển.

---

## 2. Quy Trình Thiết Kế Hệ Thống 4 Bước

### Bước 1: Khảo Sát & Xác Định Ràng Buộc (Constraints Matrix)
Làm rõ ngay với người dùng:
1. **Phần cứng**: Dùng vi điều khiển nào (ESP32, STM32F4, Raspberry Pi 4, Jetson Nano)? Cảm biến gì (IMU, Camera OV2640, DHT22, Loadcell)?
2. **Mô hình AI**: Chạy ở đâu? Chạy trực tiếp trên chip biên (TinyML/Edge AI) hay gửi ảnh/tín hiệu về Server/Web Backend để suy luận?
3. **Mạng & Giao thức**: Thiết bị kết nối qua đâu (WiFi, BLE, Zigbee, LoRa, Ethernet)? Dùng MQTT Broker nào hay REST/WebSocket trực tiếp?
4. **Giao diện Web**: Cần biểu đồ gì, điều khiển mấy relay/motor, có cần lưu lịch sử vào database không?

### Bước 2: Thiết Kế Kiến Trúc Dữ Liệu (End-to-End Data Pipeline)
1. **Tại Thiết Bị Nhúng**:
   - Tần số lấy mẫu cảm biến (ví dụ 50Hz cho rung động, 1Hz cho nhiệt độ).
   - Đóng gói dữ liệu: JSON gọn nhẹ hoặc mảng byte nhị phân.
2. **Tại Khâu Deep Learning**:
   - Tiền xử lý (FFT/Spectrogram cho âm thanh/rung động; Resize + Normalization cho ảnh).
   - Inference (chạy model tflite/onnx) → Ra nhãn (Class) và độ tin cậy (Confidence).
3. **Tại Khâu Truyền Thông**:
   - Topic MQTT mẫu: `devices/{device_id}/telemetry` (dữ liệu định kỳ), `devices/{device_id}/alert` (cảnh báo AI), `devices/{device_id}/command` (lệnh từ web xuống).
4. **Tại Web Dashboard**:
   - Lắng nghe websocket/mqtt topic để cập nhật biểu đồ và hiển thị cảnh báo ngay lập tức.

### Bước 3: Triển Khai Mã Nguồn Mẫu (Production-Grade Code)
- Luôn cung cấp mã nguồn sạch cho cả 2 hoặc 3 phía (Firmware C++ + Model Python/C-array + Web JS/HTML).
- Kèm sơ đồ nối dây (Pinout table) rõ ràng để người dùng cắm mạch không bị chập cháy.

### Bước 4: Kiểm Thử & Tối Ưu (Integration Testing & Troubleshooting)
- Kiểm tra độ trễ trọn gói (End-to-End Latency).
- Xử lý tình huống mất mạng, rớt gói tin hoặc tràn bộ nhớ.
