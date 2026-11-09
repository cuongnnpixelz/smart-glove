---
description: Quy chuẩn thiết kế giao diện Web IoT Dashboard & Giám sát telemetry thời gian thực
globs: "**/*.{html,css,js,jsx,tsx,ts,vue}"
trigger: always_on
---

# Web IoT Dashboard & Real-time Telemetry Guidelines

Tài liệu này định nghĩa tiêu chuẩn thiết kế và lập trình giao diện Web cho các hệ thống giám sát IoT, trạm điều khiển thiết bị từ xa và trực quan hóa dữ liệu AI/Cảm biến.

---

## 1. Triết Lý Thiết Kế Web IoT (Industrial & Modern Aesthetics)

- **Industrial Dark Theme làm chủ đạo**:
  - Nền tối kỹ thuật (`#0b0f19`, `#111827`), giảm mỏi mắt khi vận hành 24/7.
  - Màu sắc trạng thái trực quan rõ ràng:
    - `Success / Online / Active`: Xanh ngọc hoặc xanh neon (`#10b981`, `#00f2fe`).
    - `Warning / Threshold Alert`: Vàng cam (`#f59e0b`).
    - `Danger / Error / Offline`: Đỏ cảnh báo (`#ef4444`).
    - `Neutral / Data Lines`: Xám trung tính (`#94a3b8`, `#334155`).
- **Typography & Font Kỹ Thuật**:
  - Dùng Google Fonts hiện đại: *Inter*, *Plus Jakarta Sans* cho text chính; *JetBrains Mono* hoặc *Space Grotesk* cho các thông số số liệu, tọa độ, giá trị sensor.
- **Card-based & Grid Layout**:
  - Bố cục lưới responsive (CSS Grid / Flexbox), mỗi thiết bị hoặc cụm cảm biến là một card trực quan.
  - Bo góc vừa phải (8px - 12px), viền mỏng tinh tế (`border: 1px solid rgba(255,255,255,0.08)`).

---

## 2. Các Thành Phần Giao Diện IoT Bắt Buộc

1. **Connection Status Indicator**:
   - Luôn hiển thị trạng thái kết nối máy chủ/broker thời gian thực (ví dụ: chấm tròn xanh nhấp nháy khi `Connected`, đỏ khi `Disconnected`, vàng khi `Reconnecting`).
   - Hiển thị độ trễ (Ping / Latency tính bằng ms).

2. **Telemetry Widgets & Biểu Đồ Thời Gian Thực**:
   - Sử dụng thư viện biểu đồ hiệu năng cao, mượt mà (Chart.js với decimation, ECharts, hoặc vẽ trực tiếp trên HTML5 Canvas).
   - Biểu đồ thời gian thực (Time-series line chart): Giới hạn số điểm hiển thị (ví dụ 50 - 100 điểm gần nhất) để tránh làm lag trình duyệt khi nhận dữ liệu tần số cao (10Hz - 100Hz).
   - Radial Gauges / Progress Rings cho các đại lượng như nhiệt độ, áp suất, pin %, CPU/RAM usage.

3. **Control Actuators (Điều khiển từ xa)**:
   - Toggle Switches có phản hồi trực quan (Optimistic UI: cập nhật giao diện ngay, đổi trạng thái spinner nếu đang chờ phản hồi từ thiết bị).
   - Slider điều chỉnh tốc độ động cơ, góc servo, ngưỡng cảnh báo.
   - Nút dừng khẩn cấp (Emergency Stop - E-Stop) nổi bật, yêu cầu xác nhận khi click.

4. **Alert & Event Log Panel**:
   - Bảng log cuộn theo thời gian thực (timestamp, device ID, log level: INFO, WARN, ERROR).
   - Thông báo Toast xuất hiện ngay khi có giá trị cảm biến vượt ngưỡng an toàn.

---

## 3. Kiến Trúc Truyền Thông Phía Web Client

- **WebSocket / MQTT over WebSockets**:
  - Ưu tiên WebSocket hoặc MQTT qua WSS (`ws://` hoặc `wss://`) để cập nhật dữ liệu hai chiều với độ trễ < 50ms.
  - Cơ chế tự động kết nối lại (Auto-reconnect) với thuật toán Exponential Backoff khi mất mạng.
- **Tách biệt Data Layer và Render Layer**:
  - Không render lại toàn bộ DOM mỗi khi có một gói tin cảm biến đến. Chỉ cập nhật trực tiếp `textContent` của thẻ hiển thị hoặc gọi hàm update data của biểu đồ.
