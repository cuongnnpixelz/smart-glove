---
description: Quy tắc phát triển mô hình Deep Learning và triển khai Edge AI trên thiết bị nhúng/IoT
globs: "**/*.{py,ipynb,tflite,onnx,c,cpp,h}"
trigger: always_on
---

# Deep Learning & Edge AI Engineering Rules

Tài liệu này định nghĩa quy chuẩn phát triển mô hình Trí tuệ nhân tạo (Deep Learning) từ giai đoạn huấn luyện (Training/Fine-tuning) đến giai đoạn tối ưu hóa và triển khai trực tiếp trên phần cứng nhúng (Edge Computing / TinyML).

---

## 1. Huấn Luyện & Thiết Kế Mô Hình (Model Development)

- **Lựa chọn kiến trúc phù hợp tài nguyên**:
  - Với vi điều khiển hạn chế RAM (< 512KB SRAM như STM32F4, ESP32): Dùng TinyML, 1D-CNN, MobileNetV1/V2 thu nhỏ (alpha < 0.25), SqueezeNet, hoặc Random Forest/SVM.
  - Với Single Board Computers (Raspberry Pi, Jetson Nano, NPU Edge): Dùng YOLOv8n, MobileNetV3/V4, EfficientNet-Lite, ResNet18.
- **Tính toán Tensor Shape & Kênh (Channels)**:
  - Kiểm tra kỹ định dạng ảnh đầu vào: `NHWC` (TensorFlow/TFLite) vs `NCHW` (PyTorch/ONNX).
  - Chuẩn hóa đầu vào (Normalization): Ghi chép chính xác công thức tiền xử lý (ví dụ: `(x / 255.0)` hoặc `(x - mean) / std`) để phần nhúng thực hiện tiền xử lý đồng nhất 100%.

---

## 2. Tối Ưu Hóa & Lượng Tử Hóa (Quantization & Optimization)

- **Post-Training Quantization (PTQ) & QAT**:
  - **INT8 Quantization**: Bắt buộc lượng tử hóa từ FP32 xuống INT8 cho vi điều khiển để giảm 4 lần kích thước Flash, tiết kiệm RAM và tăng tốc độ tính toán phần cứng (tận dụng lệnh SIMD/DSP).
  - Sử dụng Representative Dataset đại diện đủ các ca thực tế khi lượng tử hóa sang INT8 để tránh suy giảm độ chính xác (Accuracy drop).
- **Xuất Định Dạng Triển Khai**:
  - TinyML/MCU: Xuất file `.tflite`, sau đó chuyển thành C-array (`unsigned char model_data[]`) bằng `xxd -i model.tflite > model_data.h`.
  - Edge Linux/SBC: Xuất sang định dạng `.onnx` hoặc engine TensorRT (`.engine`), OpenVINO IR (`.xml`/`.bin`).

---

## 3. Triển Khai Trên Thiết Bị Biên (Edge Inference)

- **Quản lý Tensor Arena / Bộ nhớ Inference**:
  - Trong TensorFlow Lite Micro (`tflite::MicroInterpreter`), `kTensorArenaSize` phải được tính toán chính xác. Nếu thiếu RAM, bộ thông dịch sẽ báo lỗi `AllocateTensors() failed`.
  - Sử dụng cơ chế đo đạc bộ nhớ tĩnh để không cấp phát bộ nhớ động trong suốt quá trình chạy inference.
- **Xử lý Trước & Sau (Pre & Post-processing)**:
  - Viết hàm tiền xử lý bằng C/C++ tối ưu hóa (fixed-point arithmetic nếu MCU không có FPU - Floating Point Unit).
  - Bounding Box / Non-Max Suppression (NMS): Viết code NMS tinh gọn, tránh cấp phát mảng động cho hàng nghìn anchor boxes.

---

## 4. Đo Đạc Hiệu Năng (Benchmarking Metrics)

Khi đánh giá mô hình Edge AI, AI **PHẢI** cung cấp các thông số định lượng cụ thể:
1. **Model Size**: Kích thước file model trên Flash (KB hoặc MB).
2. **RAM Footprint (Tensor Arena / Working Memory)**: Lượng RAM thực tế cần để chạy 1 lượt inference.
3. **Inference Latency**: Thời gian hoàn thành 1 mẫu (ms) và FPS tương ứng.
4. **Accuracy vs Precision/Recall**: Độ chính xác và tỉ lệ phát hiện thực tế.
