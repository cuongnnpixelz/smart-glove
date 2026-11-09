---
name: brainstorming
description: "Phân tích, làm rõ yêu cầu và lên phương án giải pháp kỹ thuật cho dự án IoT, Embedded, Deep Learning và Web trước khi bắt tay vào code."
risk: low
source: workspace
date_added: "2026-09-22"
---

# Brainstorming & Requirements Clarification Skill

Skill này giúp AI và người dùng cùng nhau làm rõ bài toán kỹ thuật, chọn đúng phần cứng, kiến trúc AI và stack Web phù hợp nhất với tài nguyên và mục tiêu dự án.

---

## 1. Khi Nào Kích Hoạt

- Khi người dùng có một ý tưởng chung chung (ví dụ: *"Tôi muốn làm hệ thống nhà thông minh nhận diện giọng nói offline"* hoặc *"Tôi muốn làm cánh tay robot phân loại sản phẩm bằng AI"*).
- Khi cần chọn linh kiện phần cứng, mô hình Deep Learning hoặc công nghệ truyền thông phù hợp.

---

## 2. Quy Trình Brainstorming Chuẩn

1. **Lắng nghe & Xác định mục tiêu chính**:
   - Mục tiêu cuối cùng của hệ thống là gì? (Tốc độ thời gian thực? Độ chính xác AI cao? Hay tiết kiệm pin tối đa?).
2. **Đặt câu hỏi làm rõ (Nếu còn mơ hồ)**:
   - Ưu tiên hỏi ngắn gọn, đưa ra các phương án gợi ý để người dùng chọn nhanh:
     - *Phương án MCU*: ESP32 (có sẵn WiFi/BLE, giá rẻ) hay STM32 (ổn định công nghiệp, nhiều chân ADC/Timer) hay Raspberry Pi (chạy được Linux, AI nặng)?
     - *Vị trí chạy AI*: On-device (trên chip, không cần mạng, bảo mật) hay Cloud/Server (dễ cập nhật, model lớn)?
3. **Đề xuất 2-3 Kiến Trúc Giải Pháp**:
   - Nêu rõ ưu / nhược điểm (Trade-offs) về chi phí, độ phức tạp và hiệu năng của từng phương án.
4. **Chốt Kiến Trúc (Architecture Lock)**:
   - Tóm tắt lại cấu hình đã thống nhất:
     - Phần cứng & Cảm biến.
     - Mô hình AI & Framework.
     - Giao thức truyền thông (MQTT / WebSocket / REST).
     - Giao diện Web Client.
