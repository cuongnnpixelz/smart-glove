---
description: Tự động load learnings từ .agent/learnings/ ở đầu mỗi session
globs: "**/*.{c,cpp,h,hpp,ino,py,js,ts,html,css}"
trigger: always_on
---

# Load Learnings Rule

## Khi nào áp dụng
Rule này áp dụng **tự động** mỗi khi bắt đầu một session hoặc conversation mới liên quan đến dự án này.

## Hành vi bắt buộc

### Đầu mỗi session, AI PHẢI:

1. **Đọc danh sách file** trong `.agent/learnings/` (chỉ tên file, KHÔNG đọc nội dung trước để tiết kiệm quota).

2. **Xác định** file nào liên quan đến task/câu hỏi hiện tại dựa trên tên file:
   - Task về IoT, ESP32, MQTT, C/C++ nhúng → đọc `aiot-patterns.md`, `embedded-tips.md`,...
   - Task về Deep Learning, Edge AI, TFLite, PyTorch → đọc `deep-learning-tips.md`, `model-deploy.md`,...
   - Task về Web Dashboard, UI thời gian thực → đọc `web-iot.md`, `landing-page.md`,...
   - Nếu không có file nào liên quan → bỏ qua, không đọc gì cả.

3. **Chỉ đọc nội dung** các file liên quan — KHÔNG đọc tất cả để tiết kiệm ngữ cảnh.

4. **Tóm tắt ngắn** cho user, ghi rõ tên file đã đọc:
   > "Đã đọc [số lượng] file learnings: `[tên_file.md]`"
   
   Nếu không có file nào liên quan:
   > "Không có file learnings liên quan đến task này."

5. **Áp dụng ngầm** các learnings đã đọc vào việc trả lời/thực thi — không cần hỏi lại những gì đã biết.

### Quy tắc:
- Đường dẫn chuẩn là `.agent/learnings/`.
- Nếu file learnings không tồn tại hoặc rỗng → bỏ qua, không báo lỗi.
- Không đọc lại nếu đã đọc trong cùng một session.
- Nếu task liên quan đến nhiều mảng (ví dụ: gửi dữ liệu sensor ESP32 lên Web hiển thị biểu đồ) → đọc các file tương ứng ở cả 2 mảng.
