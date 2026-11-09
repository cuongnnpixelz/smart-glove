# Giao thức Smart Glove v1

**Firmware chính hiện dùng 5 ngón:** xem [RAW5_100 và thứ tự kênh](thu-du-lieu-5-ngon.md#giao-thức).
Collector mới gửi `RAW5_100\n` để thu 100 Hz/1,5 giây. DATA5/RAW5 mặc định vẫn
25 Hz cho công cụ cũ. Mô tả DATA/RAW2 bên dưới dành cho
luồng hai ngón cũ; RAW2 chỉ lấy hai kênh đầu của firmware mới.

## Mở rộng thu dữ liệu v2

Client mới gửi `RAW2\n` sau kết nối TCP. ESP32 trả `RAW2,time_ms,flex1,flex2,ax,ay,az,gx,gy,gz`.
Không có dFlex trong gói này; client cũ vẫn nhận DATA v1. Timestamp lấy tại lúc thu,
40 ms/mẫu mục tiêu, không tạo mẫu bù giả nếu vòng lặp quá trễ.

Python v2 dùng sensor_pipeline.py để tính quaternion/body/world, lưu ADC gốc và mốc
riêng từng phiên. WebSocket giữ envelope version 1, sensor v2 có tám kênh cơ sở
`flex1,flex2,ax,ay,az,gx,gy,gz`, thêm `processed`, `calibration`, `flex1_finger`.
`processed` có các cột IMU đã tính và flex_1_norm/flex_2_norm cho chẩn đoán.
Web kiểm tra quaternion/mốc hợp lệ trước khi dùng. AI và 3D dùng cùng mốc Python.
Model v2 dùng bundle có manifest, không dùng 12-feature model cũ. Xem
[hướng dẫn v2](thu-du-lieu-v2.md); phần còn lại bên dưới mô tả DATA/model legacy.

## ESP32 ↔ Python: TCP cổng 5000

ESP32 là server, Python là client duy nhất. Mỗi bản tin kết thúc bằng `\n`.
TCP có thể chia hoặc ghép các dòng; phía nhận phải giữ bộ đệm đến khi đủ dòng.

```text
DATA,time_ms,flex1,flex2,dFlex1,dFlex2,dFlex1Avg,dFlex2Avg,ax,ay,az,gx,gy,gz
AI,XIN_CHAO,96.52
```

- Dòng `DATA` gồm tiền tố và 13 số: thời điểm + 12 đặc trưng theo đúng thứ tự trên.
- `time_ms`: thời gian từ khi ESP32 khởi động, không phải giờ máy tính.
- Flex: ADC 12 bit; `dFlex`: chênh lệch giữa hai mẫu; `dFlexAvg`: trung bình ba chênh lệch.
- Gia tốc: m/s²; gyro: rad/s. Không chuẩn hóa ADC hoặc đổi đơn vị trước khi đưa vào scaler AI.
- Mục tiêu lấy mẫu: 40 ms/mẫu (25 Hz). Kiểm tra nhịp thực tế bằng `time_ms`.
- Dòng `AI` theo chiều Python → ESP32, confidence là **0–100** để LCD hiển thị.

- Chế độ liên tục gửi `RUN,<state>\n`, với state là `CALIBRATING`, `READY`,
  `TRACKING`, `REST`, `ERROR`, `OFF` hoặc `PING`. PING giữ heartbeat, không đổi
  chữ LCD; quá 6 giây không có heartbeat thì ESP32 xóa kết quả cũ và báo mất tín
  hiệu AI. RUN không ngừng luồng RAW2. START của bộ thu sẽ thoát chế độ liên tục.
  Trong chế độ này, SEQ hiện câu và dòng `DUOI DE TIEP`; READY cho biết được làm
  lượt mới. Gián đoạn ngắn 120–500 ms trong runtime: Python bỏ chuỗi dở và gửi
  REST, giữ kết nối, chờ đoạn nghỉ mới để phục hồi hướng MPU. Lỗi dài hoặc reset
  mới kết nối/lấy mốc lại đầy đủ. Không đổi giao thức firmware cho phục hồi nhanh.

- Demo chuỗi 5 giây dùng `SEQ,XIN_CHAO\n`, `SEQ,CAM_ON\n`,
  `SEQ,TAM_BIET\n` hoặc `SEQ,NONE\n` theo chiều Python → ESP32.
  Lệnh này không có confidence. ESP32 chỉ nhận các nhãn này khi không đang thu;
  LCD hiện câu không dấu và `KET QUA CUOI`, giữ đến lượt START/kết quả mới hoặc
  mất kết nối. Không áp timeout 5 giây của luồng AI trực tiếp cho kết quả SEQ.
  `predict_sequence_v2.py` gửi quyết định cuối sau STOP, không gửi ứng viên bị loại.
- Nhãn chưa nhận diện là `NONE`; không dùng confidence của một lớp bị loại làm độ tin cậy của `NONE`.

`START\n` / `STOP\n` dành cho chương trình thu dữ liệu: ESP32 phản hồi `BEGIN\n`
/ `END\n` để đánh dấu đoạn cần lưu. Các lệnh này không đổi cấu trúc hay đơn vị
của dòng `DATA`. Không chạy chương trình thu dữ liệu đồng thời với bridge AI.

## Python → web: WebSocket cổng 8765

Mỗi WebSocket message chứa một đối tượng JSON. Mọi gói có `version: 1`,
`session_id` và `demo`. Khi ESP32 mất kết nối/khởi động lại, bridge làm mới phiên;
web bỏ dữ liệu cũ, xóa bộ lọc hướng và kết quả nhận diện của phiên trước.
Khoảng cách timestamp giữa hai mẫu trên 250 ms cũng làm mới phiên AI để không
ghép hai đoạn chuyển động bị gián đoạn vào cùng một cửa sổ 50 mẫu.

### Sensor

```json
{
  "type": "sensor",
  "version": 1,
  "session_id": "example-session",
  "seq": 42,
  "time_ms": 1680,
  "received_at_ms": 1790900000000,
  "demo": false,
  "sensors": {
    "flex1": 934, "flex2": 1061,
    "dFlex1": -3, "dFlex2": 0,
    "dFlex1Avg": 0, "dFlex2Avg": 0.33,
    "ax": -0.34, "ay": -0.012, "az": 9.208,
    "gx": -0.029, "gy": 0.056, "gz": 0.008
  }
}
```

Đây là ví dụ định dạng, không phải một phép đo hiện tại. `received_at_ms` là Unix
epoch millisecond từ máy bridge; `seq` tăng trong từng phiên. Web mặc định đổi ADC
thành độ gập bằng mốc tự động của găng hiện tại, có tùy chọn ghi mốc thủ công.
Việc này chỉ phục vụ dựng hình. Lưu lượng sensor không chờ lượt chạy AI.

### Prediction

```json
{
  "type": "prediction",
  "version": 1,
  "session_id": "example-session",
  "time_ms": 1680,
  "created_at_ms": 1790900000010,
  "prediction": "XIN_CHAO",
  "raw_label": "XIN_CHAO",
  "confidence": 0.9652,
  "accepted": true,
  "decision_reason": "accepted",
  "confidence_threshold": 0.85,
  "stable_count": 2,
  "stable_required": 2,
  "event_id": 1,
  "demo": false
}
```

- `confidence` theo thang **0–1**, luôn thuộc `raw_label`.
- Các trường chẩn đoán bổ sung tương thích v1: `decision_reason` là
  `low_confidence`, `stabilizing` hoặc `accepted`; `stable_count` / `stable_required`
  giải thích số lượt ổn định. Web cũ có thể bỏ qua các trường này.
- `accepted` chỉ đúng khi qua ngưỡng và điều kiện ổn định. Khi sai,
  `prediction` là `NONE`; không thêm lượt phát mới. Nếu đang phát một lượt đã
  chấp nhận trước đó, màn hình tiếp tục hiển thị lượt đó đến khi xong. Bảng
  Nhận diện và giọng nói vẫn hiển thị `raw_label` và confidence của nhãn thô.
- `event_id` tăng khi nhãn ổn định thay đổi, bao gồm chuyển về `NONE`.
  Khóa `(session_id, event_id)` giúp chỉ đọc một lần. Sau khi nghỉ và thực hiện
  lại cùng cử chỉ, sự kiện mới có thể được đọc.
- `NONE` luôn im lặng. Gói cũ/mất phiên hoặc dữ liệu quá hạn không được phát âm.
- Bridge gửi lại trạng thái gần nhất cho trình duyệt mới với `snapshot: true`;
  snapshot dùng để hiển thị, không phát âm lại sự kiện cũ.
- Người dùng có thể bấm Đọc lại kết quả để nghe nhãn đã chấp nhận còn mới.
  Thao tác này không tạo sự kiện AI mới và không đổi dữ liệu cảm biến.
- Web dịch `XIN_CHAO` thành **Hello**, `CAM_ON_NHIEU` thành **Thank you very much**
  và chọn giọng tiếng Anh. Nhãn giao thức vẫn giữ nguyên.
- Với mỗi sự kiện được chấp nhận, web lưu đoạn cảm biến kết thúc tại `time_ms`
  (tối đa 2 giây) và xếp vào hàng chờ phát hình/tiếng. Chỉ chuyển lượt khi đoạn
  hình và lời đọc đều xong. Lỗi loa tạm dừng lượt hiện tại để thử lại hoặc bỏ qua;
  khi tắt giọng nói, chỉ phát hình. Đổi phiên hoặc mất kết nối xóa hàng chờ.

### Status

```json
{
  "type": "status",
  "version": 1,
  "session_id": "example-session",
  "esp32_connected": true,
  "ai_state": "warming",
  "window_count": 20,
  "window_size": 50,
  "message": "Waiting for sensor window",
  "demo": false
}
```

`ai_state`: `connecting`, `warming`, `ready`, `error`, `demo`.
Status được gửi khi thay đổi và định kỳ khoảng một giây. `server_time_ms`
(nếu có) dùng để ước lượng lệch đồng hồ giữa máy web và máy Python.
Web vẫn kiểm tra thời gian từ gói sensor cuối bằng đồng hồ cục bộ; WebSocket
đang mở không có nghĩa ESP32 vẫn gửi dữ liệu.
Khi có kết quả suy luận mới, bridge gửi status cập nhật trước prediction để web
biết AI đã sẵn sàng trước khi xét kết quả đầu tiên.

Trong demo, `demo: true` và `esp32_connected: false`. Nhãn/confidence demo là
giá trị kiểm tra giao diện, không phải kết quả của mô hình đã huấn luyện.

## Nhãn chung

| Nhãn | Hiển thị/phát âm |
|---|---|
| `XIN_CHAO` | Xin chào |
| `CAM_ON_NHIEU` | Cảm ơn nhiều |
| `NONE` | Chưa nhận diện, không phát âm |

## Tài liệu đối chiếu

- [Adafruit MPU6050: đơn vị gia tốc và gyro](https://adafruit.github.io/Adafruit_MPU6050/html/class_adafruit___m_p_u6050.html)
- [MDN: WebSocket server và handshake](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_servers)
- [Arduino: các file .ino trong cùng sketch được ghép khi build](https://docs.arduino.cc/arduino-cli/sketch-build-process)
