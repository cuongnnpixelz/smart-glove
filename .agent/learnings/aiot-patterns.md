# AIoT Architecture & Integration Patterns

> Tài liệu tổng hợp các kiến trúc và mẫu code chuẩn đã kiểm chứng cho hệ thống tích hợp: Vi điều khiển (ESP32/STM32) + Deep Learning/Edge AI + MQTT/WebSockets + Web Dashboard.
> Cập nhật lần cuối: 2026-09-22

---

## 1. Architecture Patterns

### Pattern 1: Edge Telemetry to Web Real-time Dashboard
- **Luồng dữ liệu**:
  `Sensor (I2C/SPI) → ESP32 (FreeRTOS Task, Non-blocking) → MQTT Publish (JSON payload) → MQTT Broker (Mosquitto/EMQX) → Backend Web (FastAPI/Node.js or WebSocket Bridge) → Web Client (HTML5 Canvas / Chart.js Time-series Chart)`.
- **Đặc điểm**:
  - Tần số gửi 1Hz - 10Hz.
  - QoS 0 cho telemetry thông thường; QoS 1 cho trạng thái thay đổi hoặc cảnh báo nguy cấp.
  - Quản lý LWT (Last Will and Testament) để Web tự động hiển thị trạng thái `Offline` khi node mất nguồn đột ngột.

### Pattern 2: Edge AI Inference on Microcontroller (TinyML)
- **Luồng dữ liệu**:
  `Sensor Data Window (e.g. 128 samples IMU) → Preprocessing (Mean subtraction, Normalization) → TFLite Micro Interpreter (Quantized INT8 model in C-array) → ArgMax Classification → Gửi kết quả (Alert/Label) qua BLE hoặc WiFi MQTT`.
- **Bộ nhớ**:
  - Đòi hỏi tính toán `kTensorArenaSize` tĩnh, không phân mảnh Heap.
  - Dùng fixed-point arithmetic nếu MCU không có FPU.

---

## 2. Common Bugs & Hardware Solutions

### 1. ESP32 Reset liên tục khi bắt đầu kết nối WiFi
- **Triệu chứng**: Serial Monitor báo `rst:0x10 (RTCWDT_RTC_RESET)` hoặc `Brownout detector was triggered`.
- **Nguyên nhân**: Module WiFi của ESP32 tiêu thụ dòng tức thời (peak current) lên đến 400-500mA khi phát sóng, gây sụt áp đường nguồn 3.3V từ cổng USB máy tính hoặc mạch nguồn yếu.
- **Giải pháp**:
  - Gắn thêm 1 tụ hóa 100uF - 470uF song song giữa chân `3V3` và `GND` ngay gần chân module ESP32.
  - Cấp nguồn ngoài từ nguồn rời 5V/2A qua chân VIN.

### 2. Mất dữ liệu I2C hoặc treo vi điều khiển khi cảm biến ngắt kết nối
- **Nguyên nhân**: Thư viện I2C mặc định chờ tín hiệu ACK từ slave vô tận mà không có timeout.
- **Giải pháp**:
  - Thiết lập timeout cho bus I2C (ví dụ trên ESP-IDF: `i2c_master_cmd_begin(..., 1000 / portTICK_PERIOD_MS)`).
  - Đảm bảo có điện trở kéo lên (Pull-up resistors) 4.7kΩ trên đường SDA và SCL.

### 3. Model TFLite Micro dự đoán sai lệch hoàn toàn so với PyTorch lúc train
- **Nguyên nhân**: Khác biệt thứ tự kênh màu (RGB vs BGR), thiếu bước chia 255.0 hoặc tính toán sai scale/zero-point trong quá trình lượng tử hóa INT8.
- **Giải pháp**:
  - Kiểm tra metadata lượng tử hóa: `input_scale` và `input_zero_point`.
  - Công thức ánh xạ từ giá trị float sang int8: `q = (real_value / scale) + zero_point`.

### 4. Tích hợp Smart Glove Python và web 3D

- Firmware TCP `DATA,...` không phải WebSocket; chỉ một Python client đọc ESP32 rồi
  phát JSON sensor/prediction/status qua WebSocket cho trình duyệt.
- Tách đọc sensor khỏi worker TensorFlow; giới hạn hàng đợi về cửa sổ mới nhất.
  Dùng session_id để bỏ kết quả suy luận cũ sau reconnect/reset hoặc gap trên 250 ms.
- Confidence thuộc raw_label. Khi chưa chấp nhận, web phải ẩn confidence thay vì
  gán điểm của cử chỉ bị loại cho nhãn NONE. Dùng event_id cho phát âm một lần.
- Thu dữ liệu bằng luồng đọc nền liên tục; BEGIN/END đánh dấu trial, thời điểm mẫu
  đầu về 0. Không chờ người dùng nhấn Enter rồi mới đọc TCP.
- Hiệu chuẩn ADC chỉ phục vụ 3D, giữ nguyên feature AI. Mốc demo phải lưu riêng
  với mốc cảm biến thật. Gyro rad/s cần tích phân/lọc cùng gia tốc trước khi xoay tay.
- Three.js r128 tính Box3 theo hình học bind pose; để căn khung SkinnedMesh đúng,
  cập nhật skeleton và áp dụng boneTransform cho vertex khi đo bounds lúc nạp model.
- Đã xác minh bằng tests/test_bridge.py, tests/test_collector.py,
  tests/web_bridge.test.js và Chrome headless trong tests/browser_smoke.py.
- Hiệu chuẩn hai flex phải áp dụng độc lập theo từng cảm biến. Không truyền null
  cho cả hai khi một cảm biến chưa đủ mốc, vì AI vẫn có thể đọc nhãn trong khi
  cả hai ngón 3D bị ép về 0. Giữ lại mốc vừa ghi và mốc còn thiếu qua lần tải lại;
  không từ chối mốc mới chỉ vì nó trùng mốc đối diện cũ lúc hiệu chuẩn lại.
