---
name: find-bugs
description: "Chuyên gia tìm bug và xử lý sự cố trong hệ thống nhúng, mất kết nối mạng IoT, lỗi tensor Deep Learning và lỗi Web realtime"
risk: low
source: workspace
date_added: "2026-09-22"
---

# Find Bugs & Troubleshooting Skill (AIoT Systems)

Skill này kích hoạt khi người dùng gặp lỗi (Bug), hệ thống hoạt động không như mong muốn, vi điều khiển bị sập (crash/reboot), mô hình AI dự đoán sai lệch hoặc Web không nhận dữ liệu.

---

## 1. Khắc Phục Sự Cố Phần Cứng & Firmware (Embedded / MCU)

### Các dấu hiệu lỗi phổ biến & Cách kiểm tra:
1. **Vi điều khiển liên tục tự Reset (Brownout Detector / Guru Meditation / Panic)**:
   - *Nguyên nhân nguồn điện*: Nguồn cấp không đủ dòng (đặc biệt khi ESP32 bật WiFi/Bluetooth dòng đỉnh lên tới 500mA gây sụt áp). Khắc phục: thêm tụ hóa 100uF - 470uF vào chân 3V3-GND.
   - *Nguyên nhân bộ nhớ*: Tràn Stack (Stack Overflow trong FreeRTOS) hoặc rò rỉ bộ nhớ Heap.
   - *Nguyên nhân Watchdog*: Task bị treo trong vòng lặp vô tận khiến Watchdog Timer kích hoạt reset.
2. **Cảm biến không phản hồi (I2C timeout / Read 0 hoặc 255 liên tục)**:
   - Kiểm tra điện trở kéo lên (Pull-up resistors 4.7kΩ) trên đường SDA/SCL.
   - Chạy code I2C Scanner để kiểm tra đúng địa chỉ (0x68, 0x76, 0x3C...).
3. **Mất gói tin UART / Chữ bị biến dạng (Garbled characters)**:
   - Kiểm tra lệch Baudrate giữa thiết bị phát và thu.
   - Kiểm tra nối chung chân GND giữa 2 mạch.

---

## 2. Khắc Phục Sự Cố Deep Learning & Edge AI

1. **Model báo lỗi shape mismatch khi đưa vào inference**:
   - Kiểm tra thứ tự các chiều: `(Batch, Channels, Height, Width)` hay `(Batch, Height, Width, Channels)`.
   - Kiểm tra kiểu dữ liệu: `float32` hay `int8` hay `uint8`.
2. **Độ chính xác trên thực tế cực kỳ thấp so với lúc train (Accuracy collapse)**:
   - Kiểm tra tiền xử lý: Lúc train dùng ảnh RGB nhưng lúc camera nhúng chụp ra định dạng BGR hoặc YUV/Grayscale.
   - Kiểm tra chuẩn hóa: Quên chia cho 255.0 hoặc trừ mean/std không khớp.
3. **Lỗi `AllocateTensors() failed` trên TensorFlow Lite Micro**:
   - `kTensorArenaSize` không đủ lớn cho các activation buffer tạm thời. Tăng kích thước arena lên 20-50% và kiểm tra lại.

---

## 3. Khắc Phục Sự Cố Mạng IoT & Web Realtime

1. **Web Dashboard không nhận được dữ liệu (No incoming data)**:
   - Kiểm tra kết nối WebSocket / MQTT Broker: Mở tab Network / Console trên trình duyệt xem có mã lỗi `1006` (WebSocket connection failed) hoặc `ERR_CONNECTION_REFUSED`.
   - Kiểm tra Topic MQTT: Tên topic có khớp từng ký tự hoa/thường không (`sensor/temp` khác `Sensor/Temp`).
2. **Web bị đơ / CPU trình duyệt tăng vọt**:
   - Biểu đồ nhận quá nhiều dữ liệu mỗi giây mà không qua cơ chế throttle / decimation. Giới hạn số điểm vẽ tối đa và dùng `requestAnimationFrame`.
