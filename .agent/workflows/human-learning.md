---
description: Tạo tài liệu giải thích chi tiết dễ hiểu sau khi hoàn thành task kỹ thuật phức tạp
---

# Human Learning Workflow (Developer Coffee-Talk)

Sau khi hoàn thành một task phức tạp về phần cứng nhúng, tối ưu model AI hoặc kết nối mạng Web IoT, AI tạo một tài liệu giải thích thân thiện tại `.agent/learnings/human/` để bạn dễ dàng nắm bắt bản chất kỹ thuật phía sau.

---

## Cấu Trúc File Giải Thích

File được lưu tại: `.agent/learnings/human/NOTE_YYYY-MM-DD_[ten-task].md` gồm các phần:

1. **Ý Tưởng & Cách Tiếp Cận (The Core Idea)**:
   - Vì sao lại chọn kiến trúc phần cứng/phần mềm này thay vì cách khác?
2. **Những Phương Án Đã Bị Loại Bỏ (Roads Not Taken)**:
   - Những cách tiếp cận thông thường nhưng không tối ưu (ví dụ: tại sao không dùng `delay()`, tại sao không dùng model FP32 đầy đủ, tại sao chọn WebSocket thay vì HTTP polling liên tục).
3. **Mối Liên Kết Toàn Hệ Thống (How Things Connect)**:
   - Dữ liệu đi từ chân pin cảm biến → vi điều khiển xử lý/nén → gửi qua mạng → backend/AI suy luận → hiển thị lên pixel trên màn hình Web như thế nào.
4. **Lưu Ý Khi Vận Hành Thực Tế (Gotchas & Production Notes)**:
   - Những điểm cần cẩn thận khi cắm mạch thật, cấp nguồn hoặc triển khai thực tế.
