# TỔNG QUAN DỰ ÁN: GĂNG TAY THÔNG MINH NHẬN DIỆN NGÔN NGỮ KÝ HIỆU (SMART SIGN LANGUAGE GLOVE)
> **Tài liệu tổng hợp thông số kỹ thuật, kiến trúc hệ thống và thuật toán AIoT**  
> *Dùng làm dữ liệu đầu vào cho AI tra cứu tài liệu khoa học, phân tích chuyên sâu và hỗ trợ viết báo cáo / khóa luận tốt nghiệp.*

---

## 1. GIỚI THIỆU VÀ MỤC TIÊU ĐỀ TÀI

* **Tên đề tài:** Thiết kế và xây dựng hệ thống găng tay thông minh hỗ trợ giao tiếp cho người khiếm thính dựa trên công nghệ AIoT (Smart Sign Language Glove).
* **Mục tiêu:**
  1. Thu thập dữ liệu chuyển động cơ học của 5 ngón tay và tư thế cổ tay theo thời gian thực.
  2. Áp dụng kỹ thuật xử lý tín hiệu số (DSP) để loại bỏ nhiễu, chuẩn hóa góc gập và bù trôi quán tính.
  3. Huấn luyện mô hình Học máy (Machine Learning) để phân loại bảng chữ cái ngón tay và các từ vựng giao tiếp thông dụng (kết hợp chuẩn ASL 1 tay và ngôn ngữ ký hiệu Việt Nam - VSL).
  4. Nhận diện chuỗi thời gian liên tục (Continuous Sliding-window Recognition), tự động ghép từ thành câu hoàn chỉnh và chuyển đổi thành chữ viết (màn hình LCD/Web 3D) cùng giọng nói tiếng Việt (Text-to-Speech).
  5. Định hướng tối ưu hóa mô hình sang dạng TinyML để chạy trực tiếp trên vi điều khiển biên (Edge Computing).

---

## 2. KIẾN TRÚC TOÀN DIỆN CỦA HỆ THỐNG (4 TẦNG AIoT)

Hệ thống được thiết kế theo mô hình 4 tầng tích hợp:

```
+-----------------------------------------------------------------------------------+
| TẦNG 1: HARDWARE & EMBEDDED FIRMWARE (ESP32)                                      |
| - 5 Cảm biến Flex (Ngón cái -> Út) + 1 Cảm biến MPU6050 (Gia tốc & Con quay)      |
| - Đọc ADC 12-bit & I2C định thời chính xác ở tần số 100 Hz (FreeRTOS)             |
+-----------------------------------------------------------------------------------+
                                        │
                                        ▼ (Giao thức Wi-Fi TCP :5000 / USB Serial COM)
+-----------------------------------------------------------------------------------+
| TẦNG 2: DIGITAL SIGNAL PROCESSING & TRÍCH XUẤT ĐẶC TRƯNG                          |
| - Resampling lưới thời gian 1.5 giây (150 mẫu, bước 10ms)                         |
| - Lọc trung vị (Median Filter) + Chuẩn hóa Min-Max theo phiên (Open/Closed)       |
| - Tách vector trọng lực thân (Gravity Body) & Tính đạo hàm vận tốc uốn (dFlex/dt) |
+-----------------------------------------------------------------------------------+
                                        │
                                        ▼ (Vector đặc trưng 2.850 chiều)
+-----------------------------------------------------------------------------------+
| TẦNG 3: MÔ HÌNH HỌC MÁY & NHẬN DIỆN THỜI GIAN THỰC (PYTHON BACKEND)               |
| - Bộ phân loại: Scikit-learn Pipeline [StandardScaler + SVC (RBF Kernel)]         |
| - Cửa sổ trượt 1.5s, bước nhảy 250ms, bộ lọc khử rung nhãn (Streak >= 2)          |
| - Bộ máy trạng thái ghép từ thành câu tự động (Sentence State Machine)            |
+-----------------------------------------------------------------------------------+
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼ (Phản hồi TCP)                        ▼ (WebSocket :8765)
+---------------------------------------+   +---------------------------------------+
| TẦNG 4A: OUTPUT PHẦN CỨNG             |   | TẦNG 4B: GIAO DIỆN WEB & GIỌNG NÓI   |
| - Màn hình LCD 1602 I2C trên găng tay |   | - Mô phỏng bàn tay 3D (Three.js WebGL)|
| - Phản hồi trạng thái LIVE/WAIT       |   | - Phát âm tiếng Việt (Text-to-Speech) |
+---------------------------------------+   +---------------------------------------+
```

---

## 3. CHI TIẾT PHẦN CỨNG & CẤU HÌNH NGOẠI VI

### 3.1. Vi điều khiển trung tâm
* **Module:** ESP32-WROOM-32 (Dual-core Tensilica Xtensa 32-bit LX6 @ 240 MHz, 520 KB SRAM, 4 MB Flash).
* **Firmware:** [`mophong_com/mophong_com.ino`](file:///c:/Users/ACER/Downloads/doan13212%20(1)/doan13212/mophong_com/mophong_com.ino). Sử dụng FreeRTOS hỗ trợ 2 chế độ truyền nhận song song:
  - Cổng USB Serial (Baudrate 115200): Thu thập dữ liệu và debug độ trễ thấp.
  - Cổng Wi-Fi TCP Server (Port 5000): Truyền dữ liệu cảm biến không dây lên máy tính và nhận kết quả dự đoán trả về.

### 3.2. Cảm biến uốn ngón (Flex Sensors)
* **Số lượng:** 5 cảm biến gắn dọc theo 5 ngón tay (ngón cái, trỏ, giữa, áp út, út).
* **Mạch phối ghép:** Cầu phân áp với điện trở kéo xuống GND $R_{\text{pull}} = 10\text{ k}\Omega$, nguồn cấp $V_{\text{in}} = 3.3\text{ V}$.
* **Sơ đồ chân kết nối ADC (ESP32):**
  - Ngón cái (Thumb): **GPIO 32** (ADC1_CH4)
  - Ngón trỏ (Index): **GPIO 33** (ADC1_CH5)
  - Ngón giữa (Middle): **GPIO 34** (ADC1_CH6)
  - Ngón áp út (Ring): **GPIO 35** (ADC1_CH7)
  - Ngón út (Little/Pinky): **GPIO 36 / SENSOR_VP** (ADC1_CH0)
* *(Lưu ý: Toàn bộ 5 cảm biến đều được gán vào ADC1 để không bị xung đột khi bật module Wi-Fi).*

### 3.3. Cảm biến quán tính IMU (Inertial Measurement Unit)
* **Module:** MPU6050 (3 trục gia tốc kế $\pm 2g$ + 3 trục con quay hồi chuyển $\pm 250^\circ/\text{s}$).
* **Vị trí:** Gắn cố định trên mu bàn tay.
* **Giao tiếp:** I2C Hardware Bus 1:
  - **SDA:** GPIO 27
  - **SCL:** GPIO 26

### 3.4. Màn hình hiển thị trên găng
* **Màn hình:** LCD 1602 kèm module chuyển đổi I2C PCF8574 (địa chỉ mặc định `0x27`).
* **Giao tiếp:** I2C Hardware Bus 0:
  - **SDA:** GPIO 21
  - **SCL:** GPIO 22

---

## 4. XỬ LÝ TÍN HIỆU SỐ (DSP) & KỸ NGHỆ ĐẶC TRƯNG (FEATURE ENGINEERING)

Tín hiệu thô từ găng tay được xử lý qua chuỗi thuật toán toán học chuyên sâu tại [`SmartSignLanguage/sequence_model_5.py`](file:///c:/Users/ACER/Downloads/doan13212%20(1)/doan13212/SmartSignLanguage/sequence_model_5.py) trước khi đưa vào mô hình học máy:

1. **Chuẩn hóa tốc độ lấy mẫu (Linear Resampling & Interpolation):**
   - Dữ liệu thu thập ở tần số danh định **100 Hz**. Để loại bỏ hiện tượng rung nhịp (jitter) truyền thông, chuỗi dữ liệu trong cửa sổ **1.5 giây** ($1500\text{ ms}$) được nội suy cố định về lưới $150$ điểm chuẩn:
     $$\text{GRID} = [0, 10, 20, \dots, 1490]\text{ ms}$$
2. **Lọc trung vị ngón tay (5-sample Moving Median Filter):**
   - Loại bỏ các đỉnh nhiễu đột biến (impulse noise) từ bộ chuyển đổi ADC mà không làm trễ pha tín hiệu uốn.
3. **Hiệu chuẩn Co giãn Min-Max theo từng phiên (Per-session Dynamic Calibration):**
   - Khắc phục sự sai lệch khi tháo ra/đeo lại găng tay:
     $$\text{flex\_norm}_i(t) = \frac{\text{raw}_i(t) - \text{open}_i}{\text{closed}_i - \text{open}_i}$$
     *(Trong đó $\text{open}_i$ và $\text{closed}_i$ là mốc ADC đo được khi duỗi thẳng và gập tối đa ngón tay $i$).*
4. **Tách thành phần trọng lực thân (Gravity Body Decomposition):**
   - Dùng bộ lọc bù kết hợp (Complementary Filter) tách vector trọng lực trên hệ quy chiếu thân mu bàn tay ($\text{gravity}_{x,y,z}$). Đặc trưng này giữ nguyên góc nghiêng tĩnh tuyệt đối của bàn tay trong không gian 3D.
5. **Khử trôi tĩnh Con quay hồi chuyển (Gyro Bias Correction):**
   - Trừ giá trị offset đo được trong 5 giây giữ yên ban đầu:
     $$\vec{\omega}_{\text{corrected}} = \vec{\omega}_{\text{raw}} - \vec{\omega}_{\text{bias}}$$
6. **Vận tốc biến thiên góc uốn (Centered Finite Difference Velocity):**
   - Tính đạo hàm độ dốc uốn ngón tay trong khoảng thời gian đối xứng $40\text{ ms}$ để phân biệt chuyển động động và tư thế tĩnh:
     $$v_i(t) = \frac{\text{flex}_i(t+2) - \text{flex}_i(t-2)}{t_{i+2} - t_{i-2}}$$

* **Kích thước Vector đầu vào tổng thể:**
  - Mỗi bước thời gian ($10\text{ ms}$) trích xuất **19 đặc trưng**:  
    $5\text{ flex\_norm} + 3\text{ gravity\_body} + 3\text{ gyro\_corrected} + 3\text{ acc\_body} + 5\text{ dflex\_velocity}$.
  - Tổng chiều dữ liệu của một mẫu cử chỉ:  
    $$N_{\text{features}} = 150 \text{ frames} \times 19 \text{ features} = \mathbf{2.850 \text{ chiều}}.$$

---

## 5. THUẬT TOÁN HỌC MÁY & ĐÁNH GIÁ MÔ HÌNH

### 5.1. Lựa chọn thuật toán: Support Vector Machine (SVM / SVC)
* **Kiến trúc mô hình:** Pipeline Scikit-learn gồm:
  1. `StandardScaler()`: Chuẩn hóa Z-Score độc lập cho từng vị trí thời gian và đặc trưng.
  2. `SVC(C=1.0, kernel="rbf", class_weight="balanced")`: Bộ phân loại Vector hỗ trợ với hàm nhân phi tuyến RBF (Radial Basis Function).
* **Định dạng lưu trữ:** `model.joblib` (Dung lượng: **~13.95 MB**, chứa 598 Support Vectors).

### 5.2. Tại sao chọn SVM RBF thay vì Deep Learning (1D-CNN / LSTM)?
Dự án đã thực nghiệm cả hai hướng tiếp cận và rút ra kết luận khoa học quan trọng:
* **Hạn chế của Deep Learning với tập dữ liệu nhỏ:** Dự án có 559 mẫu cho 26 lớp (trung bình ~15–25 mẫu/lớp). Các mạng nơ-ron sâu (1D-CNN trong [`train_legacy.py`](file:///c:/Users/ACER/Downloads/doan13212%20(1)/doan13212/SmartSignLanguage/train_legacy.py)) bị hiện tượng **Overfitting (học vẹt)** nghiêm trọng, đạt 100% tập train nhưng dự đoán kém khi người khác đeo găng.
* **Thế mạnh của SVM RBF:** Nguyên lý tối ưu hóa khoảng cách biên (Maximum Margin Classifier) của SVM hoạt động vượt trội trên không gian đặc trưng số chiều cao (2.850 chiều) với số lượng mẫu nhỏ. Thời gian huấn luyện dưới 10 giây trên CPU, hoàn toàn xác định và không bị phụ thuộc vào tính ngẫu nhiên của khởi tạo trọng số.

### 5.3. Không gian nhãn (26 Classes)
Mô hình hiện tại phân loại chính xác **26 ký hiệu**:
* **22 Chữ cái ngón tay (Fingerspelling):** `A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, R, S, T, U, V, W`.
* **3 Từ giao tiếp thông dụng (VSL Words):** `CHAO` (Xin chào), `CAM_ON` (Cảm ơn), `TOI` (Tôi).
* **1 Trạng thái nền (Background/Rest):** `NONE` (Tư thế thả lỏng tay, không thực hiện ký hiệu).

---

## 6. CƠ CHẾ NHẬN DIỆN THỜI GIAN THỰC & GHÉP CÂU TỰ ĐỘNG

Chương trình nhận diện liên tục ([`predict_continuous_5.py`](file:///c:/Users/ACER/Downloads/doan13212%20(1)/doan13212/SmartSignLanguage/predict_continuous_5.py)) hoạt động theo cơ chế thời gian thực:

1. **Cửa sổ trượt (Sliding Window):** Duy trì hàng đợi `deque(maxlen=150)` chứa đúng 1.5 giây dữ liệu gần nhất. Mỗi bước nhảy $250\text{ ms}$, mô hình thực hiện 1 lần suy luận.
2. **Khử rung nhãn (Streak Debounce Confirmation):** Kết quả chỉ được công nhận khi có tối thiểu **2 lần dự đoán liên tiếp cùng một nhãn** (`streak >= 2`), ngăn chặn tình trạng nhảy chữ tức thời khi ngón tay đang co duỗi.
3. **Phát hiện gián đoạn mạng (Gap Detection):** Nếu khoảng cách timestamp giữa 2 gói tin vượt quá $20\text{ ms}$, hàng đợi tự động bị xóa và đợi đủ 150 mẫu mới để tránh nội suy sai lệch.
4. **Bộ máy trạng thái ghép câu (Sentence State Machine):**
   - **Nhóm câu tức thời (Instant Sentences):** Nhận diện `CHAO`, `CAM_ON` $\rightarrow$ Tự động phát âm ngay cả câu mà không cần ghép.
   - **Nhóm ghép từ tự do:** Dùng trạng thái nghỉ `NONE` ($0.5\text{s}$) làm dấu ngắt từ (Space). Khi người dùng thực hiện chuỗi `TOI` $\rightarrow$ `NONE` $\rightarrow$ `AN` $\rightarrow$ `NONE` $\rightarrow$ `COM`, các từ được đẩy vào bộ đệm `["Tôi", "ăn", "cơm"]`.
   - **Tự động chốt câu (Inactivity Timeout):** Nếu người dùng buông tay nghỉ quá **2.5 giây**, câu được chốt thành: *"Tôi ăn cơm."*, xuất ra màn hình LCD và tự động phát âm tiếng Việt qua thư viện TTS.

---

## 7. ĐỊNH HƯỚNG MỞ RỘNG & TRIỂN KHAI BIÊN (EDGE COMPUTING / TINYML)

Dự án có sẵn lộ trình nâng cấp thành thiết bị độc lập hoàn chỉnh không cần máy tính:

1. **Nâng cấp phần cứng lên ESP32-S3:**
   - Sử dụng chip ESP32-S3 với bộ tăng tốc phần cứng **Vector Instructions (PIE)** và 8MB PSRAM.
   - Kiến trúc FreeRTOS Dual-Core độc lập: Core 0 lấy mẫu 100 Hz bằng ngắt phần cứng; Core 1 chạy suy luận AI.
2. **Chuyển đổi sang TinyML (TensorFlow Lite Micro):**
   - Rút gọn mô hình thành mạng **Tiny 1D-CNN INT8** (kiến trúc tích chập 1 chiều gồm 3.500 tham số).
   - Dung lượng mô hình chỉ còn **~25 KB Flash** và **~20 KB RAM** (đã có sẵn file mẫu [`convert_int8.py`](file:///c:/Users/ACER/Downloads/doan13212%20(1)/doan13212/SmartSignLanguage/convert_int8.py) và [`tflite_to_header.py`](file:///c:/Users/ACER/Downloads/doan13212%20(1)/doan13212/SmartSignLanguage/tflite_to_header.py)).
   - Độ trễ suy luận trên chip đạt dưới **6 ms/lượt**.
3. **Phát âm thanh trực tiếp trên găng:**
   - Kết nối module giải mã âm thanh DFPlayer Mini hoặc I2S DAC (MAX98357A) cùng loa mini trên mu bàn tay để găng tự phát tiếng nói.

---

## 8. BỘ TỪ KHÓA TRA CỨU HỌC THUẬT (KEYWORDS FOR LITERATURE REVIEW)

Khi sử dụng AI hoặc Google Scholar / IEEE Xplore để tìm kiếm tài liệu tham khảo và viết bài báo cáo, hãy sử dụng các từ khóa chuyên ngành sau:

* **Từ khóa tiếng Anh (Academic / Scientific Keywords):**
  - *Smart Data Glove, Wearable Sign Language Recognition (SLR)*
  - *Flex sensor calibration, IMU drift compensation, Complementary Filter*
  - *Continuous Gesture Recognition, Sliding Window Segmentation, Co-articulation problem*
  - *Support Vector Machine (SVM) vs Convolutional Neural Networks (1D-CNN) on time-series wearable data*
  - *TinyML, TensorFlow Lite for Microcontrollers (TFLite Micro), INT8 Quantization, ESP32-S3 Edge AI*
  - *Vietnamese Sign Language (VSL), American Sign Language (ASL) Fingerspelling*
* **Từ khóa tiếng Việt:**
  - *Găng tay thông minh dịch ngôn ngữ ký hiệu, Thiết bị hỗ trợ người khiếm thính*
  - *Nhận diện cử chỉ động bằng cảm biến quán tính và cảm biến uốn*
  - *Xử lý tín hiệu chuỗi thời gian, Học máy nhúng trên vi điều khiển ESP32*

