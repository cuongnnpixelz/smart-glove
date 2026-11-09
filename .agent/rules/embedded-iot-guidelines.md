---
description: Quy chuẩn kỹ thuật bắt buộc khi lập trình vi điều khiển, hệ thống nhúng và giao thức IoT
globs: "**/*.{c,cpp,h,hpp,ino,py}"
trigger: always_on
---

# Embedded Systems & IoT Engineering Guidelines

Tài liệu này định nghĩa các nguyên tắc lập trình phần cứng & firmware để đảm bảo thiết bị hoạt động tin cậy, ổn định 24/7 trong môi trường thực tế.

---

## 1. Quản Lý Bộ Nhớ & Tài Nguyên Vi Điều Khiển

- **Hạn chế cấp phát động (Dynamic Allocation)**:
  - Tránh lạm dụng `malloc()`, `free()`, `new`, `delete` hoặc chuỗi động như `String` trong Arduino/C++ vòng lặp chính.
  - Sử dụng static buffer hoặc mảng kích thước cố định để tránh phân mảnh Heap (Heap Fragmentation) dẫn đến sập thiết bị sau vài ngày chạy.
- **Bảo vệ RAM & Stack**:
  - Khi dùng FreeRTOS, luôn tính toán Stack Size vừa đủ cho từng task (dùng `uxTaskGetStackHighWaterMark()` để theo dõi).
  - Tránh khai báo mảng lớn bên trong hàm (trên Stack); khai báo `static` hoặc cấp phát ở file scope nếu cần bộ nhớ lớn.
- **Tối ưu Flash/ROM**:
  - Sử dụng từ khóa `const` hoặc `PROGMEM` (trên AVR/ESP) để lưu trữ chuỗi tĩnh, bảng lookup, cấu hình cố định vào Flash thay vì tốn RAM.

---

## 2. Timing & Kiến Trúc Xử Lý

- **Cấm hoàn toàn Blocking Delays**:
  - Không sử dụng `delay()` trong các tác vụ cần đáp ứng nhanh hoặc trong vòng lặp chính xử lý mạng.
  - Sử dụng state machine kết hợp `millis()` hoặc FreeRTOS software timers / `vTaskDelay()`.
- **Quy tắc cho Interrupt Service Routine (ISR)**:
  - Giữ ISR ngắn nhất có thể (< vài micro-giây).
  - Không bao giờ gọi hàm `Serial.print()`, `malloc()`, `delay()` hoặc các hàm giao tiếp mạng/I2C/SPI bên trong ISR.
  - Chỉ cập nhật cờ (flags) biến `volatile` hoặc đẩy event vào FreeRTOS Queue (`xQueueSendFromISR`) và để task xử lý sau.
- **Watchdog Timer (WDT)**:
  - Luôn kích hoạt Watchdog Timer trong code production để tự động reset khi vi điều khiển gặp deadlock hoặc mất kết nối vô tận.

---

## 3. Giao Thức IoT & Truyền Nhận Dữ Liệu

- **Giao thức Mạng (MQTT / WebSocket / HTTP)**:
  - Luôn có cơ chế tự động kết nối lại (Auto-reconnect with exponential backoff) khi WiFi/Ethernet hoặc Broker bị ngắt kết nối.
  - Sử dụng QoS phù hợp trong MQTT:
    - `QoS 0`: Cho dữ liệu cảm biến định kỳ (mất vài gói không ảnh hưởng).
    - `QoS 1`: Cho cảnh báo quan trọng, trạng thái relay, thay đổi cấu hình.
  - Quản lý Last Will and Testament (LWT) trong MQTT để báo trạng thái `offline` cho Web Dashboard ngay khi thiết bị mất nguồn đột ngột.
- **Đóng gói Payload**:
  - Giữ kích thước payload nhỏ gọn.
  - Chỉ gửi các trường cần thiết: `{"temp":28.5,"hum":65.2,"ts":1710000000}`.
  - Với các mạng băng thông hẹp (LoRa, BLE), mã hóa sang dạng nhị phân (packed struct / Protocol Buffers).

---

## 4. Ngoại Vi & Giao Tiếp Phần Cứng (I2C, SPI, UART)

- **I2C**: Luôn có timeout khi đọc dữ liệu I2C để tránh treo chip nếu cảm biến bị tuột dây (SCL/SDA bị kéo xuống GND).
- **UART**: Xử lý ring buffer hoặc DMA để không bỏ sót byte dữ liệu khi truyền tốc độ cao.
- **Chống rung phím (Debounce)**: Luôn áp dụng debounce (phần mềm 20-50ms hoặc phần cứng RC) cho nút nhấn cơ học và tín hiệu công tắc hành trình.
