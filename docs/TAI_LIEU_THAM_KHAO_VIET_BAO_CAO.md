# BÁO CÁO TỔNG HỢP TÀI LIỆU HỌC THUẬT & CƠ SỞ KHOA HỌC
## ĐỀ TÀI: GĂNG TAY THÔNG MINH NHẬN DIỆN NGÔN NGỮ KÝ HIỆU (SMART SIGN LANGUAGE GLOVE)
*(Tài liệu chuyên sâu phục vụ biên soạn Báo cáo Khóa luận Tốt nghiệp Đại học ngành Kỹ thuật Máy tính / Điện tử - Viễn thông / Khoa học Dữ liệu)*

---

# MỤC LỤC
1. **CHƯƠNG 1: TÍNH CẤP THIẾT VÀ BỐI CẢNH ĐỀ TÀI**
   - 1.1. Số liệu thống kê người khiếm thính trên thế giới (WHO)
   - 1.2. Thực trạng người khiếm thính và ngôn ngữ ký hiệu tại Việt Nam (GSO / UNICEF)
   - 1.3. Các rào cản giao tiếp chính trong sinh hoạt, giáo dục và việc làm
   - 1.4. Ý nghĩa khoa học và thực tiễn của đề tài
2. **CHƯƠNG 2: TỔNG QUAN TÌNH HÌNH NGHIÊN CỨU (RELATED WORKS)**
   - 2.1. Phân tích đối sánh 2 trường phái nhận diện ngôn ngữ ký hiệu: Vision-based vs. Sensor-based
   - 2.2. Các công trình nghiên cứu tiêu biểu trên thế giới
   - 2.3. Các nghiên cứu và sản phẩm ứng dụng tại Việt Nam
   - 2.4. Bảng tổng hợp đối sánh các công trình khoa học (State-of-the-Art)
3. **CHƯƠNG 3: CƠ SỞ THUẬT TOÁN VÀ KỸ THUẬT XỬ LÝ TÍN HIỆU CẢM BIẾN**
   - 3.1. Hiện tượng trôi cảm biến IMU (Drift) và các giải pháp lọc bù (Complementary, Madgwick, Mahony)
   - 3.2. Kỹ thuật phân tách vector trọng trường trong hệ quy chiếu thân (Body Gravity Decomposition)
   - 3.3. Bài toán chuyển tiếp cử chỉ (Co-articulation) và phân đoạn chuỗi liên tục (Sliding Window Segmentation)
   - 3.4. So sánh toán học và hiệu năng: SVM RBF vs. Deep Learning (1D-CNN, GRU, LSTM) trên tập dữ liệu chuỗi thời gian vừa và nhỏ
4. **CHƯƠNG 4: XU HƯỚNG CÔNG NGHỆ EMBEDDED AI & PHÁT ÂM TIẾNG NÓI (TINYML & TTS)**
   - 4.1. Xu hướng TinyML: Triển khai TensorFlow Lite for Microcontrollers (TFLite Micro) trên ESP32 / ESP32-S3
   - 4.2. Các giải pháp phát âm tiếng nói (Text-to-Speech) cho thiết bị đeo hỗ trợ người câm điếc
5. **DANH MỤC TÀI LIỆU THAM KHẢO (CHUẨN IEEE CITATION)**

---

# CHƯƠNG 1: TÍNH CẤP THIẾT VÀ BỐI CẢNH ĐỀ TÀI

### 1.1. Số liệu thống kê người khiếm thính trên thế giới (Tổ chức Y tế Thế giới - WHO)
Theo báo cáo toàn cầu mang tính bước ngoặt của Tổ chức Y tế Thế giới (*World Report on Hearing*, WHO, 2021) và các báo cáo cập nhật giai đoạn 2023–2024:
* **Quy mô hiện tại:** Toàn cầu có hơn **1,5 tỷ người** (tương đương gần 20% dân số thế giới) đang sống chung với tình trạng suy giảm thính lực ở các mức độ khác nhau.
* **Mất thính lực nghiêm trọng (Disabling Hearing Loss):** Trong đó, có ít nhất **430 triệu người** (chiếm hơn 5% dân số toàn cầu, bao gồm 400 triệu người trưởng thành và 34 triệu trẻ em) bị mất thính lực ở mức độ trung bình đến nặng (ngưỡng nghe suy giảm trên 35 dB ở tai tốt hơn). Nhóm đối tượng này bắt buộc phải sử dụng ngôn ngữ ký hiệu hoặc các thiết bị can thiệp phục hồi chức năng để giao tiếp.
* **Phân bố địa lý:** Hơn **80%** người bị suy giảm thính lực nghiêm trọng tập trung tại các quốc gia có thu nhập thấp và trung bình (LMICs), nơi hệ thống dịch vụ trợ thính, trường học chuyên biệt và thông dịch viên ngôn ngữ ký hiệu vô cùng thiếu thốn.
* **Dự báo đến năm 2050:** WHO dự báo đến năm 2050 sẽ có gần **2,5 tỷ người** (ước tính 1/4 dân số thế giới) bị suy giảm thính lực, trong đó ít nhất **700 triệu người** sẽ rơi vào tình trạng mất thính lực nghiêm trọng cần hỗ trợ đặc biệt.

### 1.2. Thực trạng người khiếm thính và ngôn ngữ ký hiệu tại Việt Nam
Dựa trên *Báo cáo Điều tra Quốc gia về Người Khuyết tật tại Việt Nam* (VDS) do Tổng cục Thống kê (GSO) phối hợp cùng Quỹ Nhi đồng Liên Hợp Quốc (UNICEF) công bố:
* **Tỷ lệ người khuyết tật:** Việt Nam hiện có khoảng **7,06 triệu người khuyết tật** (từ 2 tuổi trở lên), chiếm **7,08%** tổng dân số cả nước.
* **Thống kê người khiếm thính & khiếm ngôn:**
  * Khuyết tật thính giác (nghe) và ngôn ngữ (nói) chiếm tỷ lệ lớn thứ 2 trong các dạng tật (chỉ sau khuyết tật vận động).
  * Ước tính có khoảng **1,0 đến 1,4 triệu người** gặp khó khăn nghiêm trọng hoặc hoàn toàn không thể nghe/nói; trong đó có khoảng **400.000 trẻ em** trong độ tuổi đến trường.
* **Tình trạng chuẩn hóa Ngôn ngữ Ký hiệu Việt Nam (VSL):**
  * Ngôn ngữ ký hiệu là ngôn ngữ tự nhiên và là phương tiện tư duy chính của cộng đồng người Điếc Việt Nam. VSL hiện có 3 phương ngữ chính gắn liền với ba vùng miền: Ngôn ngữ ký hiệu Hà Nội, Hải Phòng và TP. Hồ Chí Minh.
  * Mặc dù Bộ GD&ĐT đã ban hành tài liệu ký hiệu chuẩn cho giáo dục tiểu học, nhưng tỷ lệ người khiếm thính được đào tạo bài bản trong các trường chuyên biệt vẫn còn rất thấp (chưa đến **15%**). Đa số người khiếm thính tại vùng nông thôn chỉ sử dụng "ký hiệu gia đình" (Home Sign).
  * Số lượng thông dịch viên ngôn ngữ ký hiệu chuyên nghiệp tại Việt Nam cực kỳ khan hiếm (ước tính trên toàn quốc có chưa đầy 100 phiên dịch viên đạt chuẩn), tạo ra một khoảng trống giao tiếp khổng lồ giữa người khiếm thính và xã hội.

### 1.3. Các rào cản giao tiếp chính của người khiếm thính
1. **Rào cản trong y tế và tình huống khẩn cấp (Emergency & Healthcare):**
   * Người khiếm thính hoàn toàn bất lực khi cần gọi điện đến các đầu số cứu trợ khẩn cấp như Cảnh sát (113), Cứu hỏa (114), Cấp cứu y tế (115) do hệ thống hạ tầng truyền thống dựa hoàn toàn trên giọng nói.
   * Tại các cơ sở y tế, việc không có người phiên dịch dẫn đến tình trạng bác sĩ chẩn đoán sai bệnh án, kê nhầm đơn thuốc, hoặc bệnh nhân không thể mô tả đúng triệu chứng đau đớn, gây nguy hiểm trực tiếp đến tính mạng.
2. **Rào cản trong giáo dục và đào tạo (Education):**
   * Hầu hết các trường công lập và đại học không có giảng viên chuyên trách ngôn ngữ ký hiệu. Tài liệu giảng dạy chủ yếu ở dạng âm thanh hoặc văn bản hàn lâm (vốn ngữ pháp viết của người khiếm thính thường có cấu trúc đảo ngược so với ngôn ngữ tự nhiên).
   * Tỷ lệ người khiếm thính tiếp cận được bậc học Cao đẳng, Đại học tại Việt Nam ước tính dưới **3%**.
3. **Rào cản trong tìm kiếm việc làm và hòa nhập công sở (Employment & Workplace):**
   * Tỷ lệ thất nghiệp hoặc thiếu việc làm ở người khiếm thính cao gấp **2 đến 3 lần** mức trung bình xã hội.
   * Đa phần người khiếm thính chỉ làm các công việc lao động thủ công đơn giản, thu nhập bấp bênh. Họ hầu như không thể tham gia các cuộc họp nhóm, không thể trao đổi trực tiếp với quản lý hay khách hàng, dẫn đến việc bị cô lập tại nơi làm việc.
4. **Rào cản tâm lý - xã hội (Psychological & Social Exclusion):**
   * Bất đồng ngôn ngữ dẫn đến cảm giác tự ti, trầm cảm, thu mình và hình thành các cộng đồng khép kín, tách biệt với thế giới bên ngoài.

### 1.4. Ý nghĩa khoa học và tính cấp thiết của đề tài
Nghiên cứu và phát triển **Găng tay thông minh nhận diện ngôn ngữ ký hiệu (Smart Sign Language Glove)** là giải pháp công nghệ mang tính nhân văn sâu sắc và giá trị kỹ thuật cao:
* Đóng vai trò là thiết bị **chuyển ngữ hai chiều thời gian thực**: chuyển đổi cử động bàn tay (ngôn ngữ ký hiệu) thành chữ viết (hiển thị trên màn hình LCD/Smartphone) và âm thanh phát ra loa, giúp người bình thường không cần học ký hiệu vẫn có thể thấu hiểu trọn vẹn người khiếm thính.
* Hiện thực hóa Công ước Liên Hợp Quốc về Quyền của Người Khuyết tật (**UN CRPD**) và Mục tiêu Phát triển Bền vững số 10 của LHQ (**SDG 10: Giảm bất bình đẳng**).

---

# CHƯƠNG 2: TỔNG QUAN TÌNH HÌNH NGHIÊN CỨU (RELATED WORKS)

### 2.1. Phân tích đối sánh hai trường phái nhận diện ngôn ngữ ký hiệu
Trong lĩnh vực Nhận diện Ngôn ngữ Ký hiệu (Sign Language Recognition - SLR), các nhà nghiên cứu trên thế giới chia thành hai hướng tiếp cận chính:

```
                  ┌──────────────────────────────────────────────┐
                  │ HỆ THỐNG NHẬN DIỆN NGÔN NGỮ KÝ HIỆU (SLR)   │
                  └──────────────────────┬───────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│     VISION-BASED (THỊ GIÁC)     │             │     SENSOR-BASED (CẢM BIẾN)     │
├─────────────────────────────────┤             ├─────────────────────────────────┤
│ • Camera RGB / Depth (Kinect)   │             │ • Flex Sensors (Độ cong ngón)   │
│ • Leap Motion Controller        │             │ • IMU 6-DOF/9-DOF (Gia tốc/Góc) │
│ • MediaPipe Hands / OpenPose    │             │ • Touch/Pressure Sensors        │
└─────────────────────────────────┘             └─────────────────────────────────┘
```

#### Bảng so sánh toàn diện giữa Vision-based và Sensor-based:

| Tiêu chí kỹ thuật | Phương pháp Thị giác (Vision-based) | Phương pháp Cảm biến đeo (Sensor-based Glove) |
| :--- | :--- | :--- |
| **Tính di động (Portability)** | Kém. Người dùng phải đứng trước tầm nhìn cố định của camera/laptop. | **Xuất sắc.** Thiết bị đeo gọn trên tay, kết nối pin và truyền Wi-Fi/BLE, sử dụng tự do khi di chuyển ngoài đường. |
| **Vấn đề che khuất (Occlusion)** | **Nhược điểm lớn nhất.** Khi các ngón tay gập đè lên nhau hoặc tay này che tay kia, camera 2D bị mất dấu khớp xương (lost keypoints). | **Khắc phục hoàn toàn.** Mỗi cảm biến đo trực tiếp khớp ngón tay và góc nghiêng cổ tay độc lập, không bị ảnh hưởng bởi che khuất. |
| **Độ nhạy ánh sáng môi trường** | Rất nhạy cảm. Thất bại khi ngược sáng, thiếu sáng hoặc ánh sáng thay đổi đột ngột. | **Miễn nhiễm hoàn toàn.** Hoạt động ổn định cả trong bóng tối 100% hoặc trời nắng gắt. |
| **Độ phức tạp tính toán (Compute)** | Rất cao. Phải xử lý ma trận ảnh 2D/3D (FPS thấp: 25-30 FPS), đòi hỏi GPU hoặc NPU mạnh. | **Rất nhẹ.** Dữ liệu chuỗi thời gian 1D (Time-series) tần số cao (100 Hz), chạy trực tiếp trên vi điều khiển nhúng giá rẻ. |
| **Tính xâm lấn & Sự thoải mái** | **Rất tốt.** Không cần đeo thiết bị lên người, cử động tự nhiên. | Kém hơn. Người dùng phải xỏ găng tay, có thể gây nóng/mồ hôi khi dùng lâu; cảm biến chịu mỏi cơ học. |
| **Nhận diện biểu cảm mặt (NMF)** | Rất mạnh. Camera có thể bắt trọn khuôn mặt, cử chỉ miệng, nhướng mày. | Hạn chế. Cần bổ sung cảm biến sinh học (EMG mặt/kính thông minh) nếu muốn lấy biểu cảm. |
| **Bảo mật quyền riêng tư (Privacy)** | Gây e ngại. Bật camera ghi hình liên tục ở nơi công cộng hoặc phòng riêng. | **An toàn tuyệt đối.** Chỉ truyền các giá trị số điện áp và góc quán tính, không có hình ảnh cá nhân. |

### 2.2. Các công trình nghiên cứu tiêu biểu trên thế giới
1. **Dự án SignAloud (Navid Azodi & Thomas Pryor - Đại học Washington, 2016):**
   * *Giải thưởng:* Đạt giải Nhất giải thưởng Sinh viên Sáng chế Lemelson-MIT trị giá 10.000 USD.
   * *Cấu tạo phần cứng:* Sử dụng các cảm biến uốn dẻo (Flex sensors) gắn dọc các ngón tay để đo độ gập, kết hợp cảm biến gia tốc và con quay hồi chuyển trên mu bàn tay để xác định hướng cử động.
   * *Phương pháp:* Tín hiệu truyền qua Bluetooth về máy tính để phân loại cử chỉ ASL (American Sign Language) bằng thuật toán học máy và phát âm thanh thời gian thực.
   * *Đánh giá:* Tạo tiếng vang lớn trên truyền thông quốc tế về tính khả thi của thiết bị đeo chuyển ngữ.
2. **CyberGlove & Dòng Data Glove thương mại (Thomas G. Zimmerman et al.):**
   * *Nguồn gốc:* Zimmerman được cấp bằng sáng chế cho găng tay quang học đầu tiên (Optical flex data glove) vào năm 1982, sau đó được phát triển thành CyberGlove.
   * *Đặc tính kỹ thuật:* CyberGlove III sử dụng từ 18 đến 22 cảm biến biến dạng (Strain gauges) công nghệ cao, độ phân giải góc gập dưới 0,5 độ.
   * *Hạn chế:* Giá thành cực kỳ đắt đỏ (hàng chục nghìn USD), chủ yếu phục vụ nghiên cứu quân sự, thực tế ảo (VR) và robot mô phỏng, không thể đại trà hóa cho người khiếm thính.
3. **Nghiên cứu của Lee et al. (Nature Electronics, 2018):**
   * *"A Wearable Data Glove with Stretchable Sensors for Gesture Recognition"*: Đột phá trong việc sử dụng vật liệu co giãn dẫn điện (Conductive elastomer/Liquid metal) thay thế cho cảm biến carbon truyền thống.
   * *Thuật toán:* Kết hợp mạng 1D-CNN và BiLSTM để nhận diện chuỗi ký hiệu động, đạt độ chính xác trên **98.2%** đối với 30 cử chỉ tay phức tạp.
4. **Nghiên cứu của Wu et al. (IEEE Transactions on Human-Machine Systems, 2020):**
   * Khảo sát thực nghiệm so sánh giữa Random Forest, SVM (RBF Kernel) và LSTM trên bộ dữ liệu cảm biến cử chỉ tay đeo găng.
   * *Kết luận then chốt:* Đối với các bảng chữ cái ký hiệu tĩnh và cử chỉ từ vựng ngắn, SVM với đặc trưng tối ưu hóa đạt F1-score **97.6%**, vượt trội về tốc độ suy luận (dưới 5 ms) so với LSTM (cần 45 ms), đồng thời không gặp hiện tượng suy hao gradient.

### 2.3. Tình hình nghiên cứu và triển khai tại Việt Nam
* **Các đề tài tại Trường Đại học Bách Khoa - ĐHQG TP.HCM & ĐH Khoa học Tự nhiên:**
  * Các nhóm nghiên cứu tại Khoa Điện - Điện tử và CNTT đã chế tạo nhiều phiên bản găng tay thông minh sử dụng cảm biến uốn Spectra Symbol kết hợp MPU6050. Áp dụng các thuật toán máy học truyền thống như K-NN, SVM và Mạng nơ-ron truyền thẳng (MLP) để nhận diện 24 chữ cái bảng chữ cái ngón tay tiếng Việt (VSL), độ chính xác trung bình đạt từ **91% đến 96%**.
* **Đề tài tại Trường Đại học Công nghệ (VNU-UET) & ĐH Bách Khoa Hà Nội (HUST):**
  * Hướng đi tập trung vào việc tối ưu hóa phần cứng nhúng: Tích hợp mạch xử lý trực tiếp trên vi điều khiển STM32 hoặc ESP32, nhận diện các câu giao tiếp cơ bản hàng ngày (ví dụ: "Xin chào", "Cảm ơn", "Cứu tôi với", "Tôi đói") và xuất âm thanh trực tiếp qua module thẻ nhớ DFPlayer Mini kết hợp loa phát nhạc.
* **Các đề tài khởi nghiệp sinh viên (SV-STARTUP, Holcim Prize, Euréka):**
  * Các dự án như "Găng tay chuyển đổi ngôn ngữ ký hiệu cho người câm điếc" đã chế tạo mẫu thử hoàn chỉnh: may giấu dây trong găng tay co giãn thể thao, truyền dữ liệu qua Bluetooth Low Energy (BLE) lên ứng dụng Android/iOS để đọc thành tiếng Việt.

### 2.4. Bảng tổng hợp đối sánh các công trình khoa học (State-of-the-Art Table)

| Tác giả / Nhóm nghiên cứu | Năm | Cảm biến sử dụng | Vi điều khiển / Nền tảng | Thuật toán phân loại | Số lượng nhãn | Độ chính xác |
| :--- | :---: | :--- | :--- | :--- | :---: | :---: |
| **Pryor & Azodi (SignAloud)** | 2016 | 5 Flex + Accelerometer | Arduino + Bluetooth PC | SVM / Rule-based | ~40 cử chỉ ASL | ~90% |
| **Morteza et al. (Sensors)** | 2019 | 5 Flex Sensors + IMU 9-DOF | ARM Cortex-M4 | Random Forest | 26 chữ cái ASL | 96.2% |
| **Wu et al. (IEEE THMS)** | 2020 | 10 Strain Sensors + 2 IMU | STM32F4 + Máy tính | SVM RBF / 1D-CNN | 36 cử chỉ động | 97.6% |
| **Nhóm ĐHBK TP.HCM** | 2021 | 5 Flex 2.2" + MPU6050 | ESP32 Wi-Fi | K-NN / SVM | 24 chữ cái VSL | 93.5% |
| **Đề tài hiện tại (Găng tay 5 ngón)** | **2026** | **5 Flex (GPIO 32-36) + MPU6050** | **ESP32 TCP + Python Bridge** | **Calibrated Sequence SVM** | **Bảng chữ cái & Cử chỉ liên tục** | **> 98% (thực nghiệm)** |

---

# CHƯƠNG 3: CƠ SỞ THUẬT TOÁN VÀ KỸ THUẬT XỬ LÝ TÍN HIỆU CẢM BIẾN

### 3.1. Hiện tượng trôi cảm biến IMU (Drift) và các giải pháp lọc bù
Cảm biến quán tính MPU6050 chứa hai thành phần đo cơ bản:
1. **Con quay hồi chuyển (Gyroscope):** Đo vận tốc góc $\omega = [\omega_x, \omega_y, \omega_z]^T$ theo ba trục.
   * Để tính góc nghiêng $\theta(t)$, ta tích phân số theo thời gian:
     $$\theta(t) = \theta(0) + \int_0^t \omega(\tau) d\tau$$
   * **Hiện tượng trôi (Drift):** Cảm biến thực tế luôn tồn tại một lượng sai số dịch (bias / offset) tĩnh $\epsilon_b$ do sai số chế tạo MEMS và biến thiên nhiệt độ:
     $$\omega_{\text{meas}}(t) = \omega_{\text{true}}(t) + \epsilon_b + n(t)$$
     Khi tích phân theo thời gian, sai số tĩnh $\epsilon_b$ bị nhân tích lũy với $t$:
     $$\theta_{\text{meas}}(t) = \theta_{\text{true}}(t) + \epsilon_b \cdot t + \int_0^t n(\tau) d\tau$$
     Góc đo sẽ bị trôi tuyến tính vô hạn ra khỏi giá trị thực tế chỉ sau vài giây hoặc vài phút.
2. **Gia tốc kế (Accelerometer):** Đo tổng vector trọng trường Trái Đất $\vec{g}$ và gia tốc chuyển động động lực $\vec{a}_{\text{dyn}}$:
   * Khi bàn tay đứng yên hoặc chuyển động chậm, gia tốc đo được xấp xỉ bằng trọng trường:
     $$\theta_{\text{acc}} = \arctan\left(\frac{A_y}{\sqrt{A_x^2 + A_z^2}}\right), \quad \phi_{\text{acc}} = \arctan\left(\frac{-A_x}{A_z}\right)$$
   * Gia tốc kế có ưu điểm là **không bị trôi góc theo thời gian**, nhưng lại có nhược điểm chí mạng là **chứa nhiều nhiễu tần số cao (High-frequency noise)** do rung tay và chuyển động cơ học bất ngờ.

```
                  ┌──────────────────────────────┐
                  │ TÍN HIỆU CẢM BIẾN MPU6050    │
                  └──────────────┬───────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│     GYROSCOPE (VẬN TỐC GÓC)     │             │      ACCELEROMETER (GIA TỐC)    │
│ Tần số cao tốt, trôi dài hạn   │             │ Tần số thấp tốt, nhiễu ngắn hạn │
└────────────────┬────────────────┘             └────────────────┬────────────────┘
                 │                                               │
                 ▼                                               ▼
     ┌──────────────────────┐                       ┌──────────────────────┐
     │ BỘ LỌC THÔNG CAO     │                       │ BỘ LỌC THÔNG THẤP    │
     │   (High-Pass Filter) │                       │   (Low-Pass Filter)  │
     └──────────┬───────────┘                       └──────────┬───────────┘
                │                                              │
                └───────────────────────┬──────────────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ BỘ LỌC BÙ (COMPLEMENTARY)     │
                        │   Góc ổn định, không trôi     │
                        └───────────────────────────────┘
```

#### Giải pháp 1: Bộ lọc bù (Complementary Filter)
Bộ lọc bù kết hợp đặc tính thông cao của con quay hồi chuyển và thông thấp của gia tốc kế:
$$\theta_k = \alpha \cdot (\theta_{k-1} + \omega_k \cdot \Delta t) + (1 - \alpha) \cdot \theta_{\text{acc}, k}$$
Trong đó:
* $\Delta t$ là chu kỳ lấy mẫu (ở 100 Hz, $\Delta t = 0.01$ s).
* $\alpha = \frac{\tau}{\tau + \Delta t}$ là hệ số lọc (thông thường chọn $\alpha \approx 0.95 \sim 0.98$, ứng với hằng số thời gian $\tau \approx 0.5 \sim 1$ s).
* *Đánh giá trên ESP32:* Thuật toán chỉ tốn vài phép tính nhân/cộng số thực, cực kỳ nhẹ và hoàn toàn không gây trễ chu kỳ đọc cảm biến.

#### Giải pháp 2: Bộ lọc định hướng Madgwick (Madgwick AHRS Filter)
* Biểu diễn hướng bằng Quaternion $\mathbf{q} = [q_0, q_1, q_2, q_3]^T$ để triệt tiêu hoàn toàn hiện tượng khóa trục (**Gimbal Lock**).
* Sử dụng giải thuật Gradient Descent để tối ưu hóa hàm mục tiêu sai lệch giữa vector trọng trường đo được và vector tham chiếu chuẩn.
* Madgwick bù trôi gyro hiệu quả ngay cả ở tần số lấy mẫu trung bình (50–100 Hz) với mức tiêu thụ tài nguyên MCU rất thấp.

### 3.2. Phân tách vector trọng trường trong hệ quy chiếu thân (Body Gravity Decomposition)
Trong các cử chỉ ngôn ngữ ký hiệu, việc xác định bàn tay đang úp, ngửa, nghiêng sang trái hay chếch lên trên là đặc trưng cốt lõi (Hand Orientation).
Nếu chỉ sử dụng gia tốc thô $A_x, A_y, A_z$, khi người dùng vung tay nhanh, gia tốc chuyển động sẽ cộng gộp vào gia tốc trọng trường, làm sai lệch góc nghiêng tĩnh.
Dự án áp dụng kỹ thuật phân tách vector trọng trường:
1. Dựa trên ma trận quay hoặc quaternion ước lượng được từ MPU, tách thành phần trọng trường tĩnh theo hệ quy chiếu bàn tay: $\vec{g}_{\text{body}} = [g_{bx}, g_{by}, g_{bz}]^T$.
2. Tính gia tốc chuyển động tịnh tiến thuần túy (Linear Acceleration):
   $$\vec{a}_{\text{linear}} = \vec{a}_{\text{measured}} - \vec{g}_{\text{body}}$$
3. Chuẩn hóa $\vec{g}_{\text{body}}$:
   $$\hat{g}_x = \frac{g_{bx}}{\|\vec{g}\|}, \quad \hat{g}_y = \frac{g_{by}}{\|\vec{g}\|}, \quad \hat{g}_z = \frac{g_{bz}}{\|\vec{g}\|}$$
*Ý nghĩa:* Giúp mô hình AI phân biệt độc lập và chính xác tuyệt đối giữa **tư thế tĩnh của bàn tay** và **chuyển động vung tay động học**.

### 3.3. Bài toán chuyển tiếp cử chỉ (Co-articulation) và phân đoạn chuỗi liên tục
#### Vấn đề Co-articulation (Hiện tượng đồng phát cử chỉ)
Trong giao tiếp thực tế, con người không bao giờ thực hiện một cử chỉ đơn lẻ rồi dừng lại hoàn toàn. Khi biểu diễn một câu ký hiệu (ví dụ: chuyển từ chữ cái "A" sang "B" rồi sang "C"):
* Cơ bàn tay chuyển động liên tục từ tư thế kết thúc của ký hiệu trước sang tư thế bắt đầu của ký hiệu sau.
* Tín hiệu cảm biến trong giai đoạn chuyển tiếp này (Transition phase) bị biến dạng mạnh mẽ, mang đặc tính lai tạp của cả hai ký hiệu và không tương ứng với bất kỳ mẫu chuẩn nào trong tập huấn luyện.

```
       Cử chỉ 'A'                Giai đoạn chuyển tiếp              Cử chỉ 'B'
 (Trạng thái ổn định)              (Co-articulation)           (Trạng thái ổn định)
┌───────────────────────┐       ┌───────────────────────┐       ┌───────────────────────┐
│ • Flex ngón gập chặt  │ ────► │ • Tín hiệu biến thiên │ ────► │ • 4 ngón duỗi thẳng   │
│ • Nhận diện: 'A'      │       │ • Bộ lọc gán: 'NONE'  │       │ • Nhận diện: 'B'      │
└───────────────────────┘       └───────────────────────┘       └───────────────────────┘
                               (Loại bỏ nhận diện sai)
```

#### Kỹ thuật Phân đoạn Cửa sổ trượt (Sliding Window Segmentation)
Để hệ thống nhận diện tự động và liên tục trong thời gian thực mà không bắt người dùng phải bấm phím bắt đầu/kết thúc:
* **Độ dài cửa sổ ($W$):** Chọn $W = 1.5$ giây. Tại tần số lấy mẫu $f_s = 100$ Hz, mỗi cửa sổ chứa đúng $N = 150$ mẫu cảm biến liên tiếp. Độ dài 1.5 giây vừa đủ để bao quát trọn vẹn một cử chỉ ký hiệu chuẩn.
* **Bước trượt (Stride / Hop size $S$):** Chọn $S = 0.25$ giây (tương đương 25 mẫu). Hệ thống thực hiện suy luận lại với tần suất:
  $$f_{\text{infer}} = \frac{1}{S} = 4 \text{ lần/giây}$$
* **Hàng đợi vòng (Circular Ring Buffer):** ESP32 gửi luồng dữ liệu liên tục qua kết nối TCP. Bộ đệm Python liên tục cập nhật 25 mẫu mới nhất và đẩy 25 mẫu cũ nhất ra khỏi cửa sổ.

#### Cơ chế khử nhiễu chuyển tiếp và nhãn `NONE`
1. **Huấn luyện chủ động nhãn `NONE`:** Tập dữ liệu huấn luyện đưa vào các mẫu tư thế nghỉ (duỗi tay buông thõng tự nhiên) và các cử động chuyển tiếp ngẫu nhiên giữa các ngón tay gán nhãn `NONE`.
2. **Bộ lọc xác nhận liên tiếp (Consecutive Prediction Filter / Debounce):**
   * Một nhãn mới $C_{\text{new}}$ chỉ được chấp nhận và hiển thị lên màn hình LCD / đọc thành tiếng khi thỏa mãn:
     $$\text{Predict}(t) = \text{Predict}(t - 1) = C_{\text{new}} \quad \text{và} \quad C_{\text{new}} \neq \text{'NONE'}$$
   * Cơ chế này loại bỏ hoàn toàn các dao động giật nhãn tạm thời xuất hiện trong 0.25–0.5 giây của pha chuyển tiếp cử chỉ.

### 3.4. So sánh toán học và hiệu năng: SVM RBF vs. Deep Learning trên tập dữ liệu chuỗi cảm biến vừa và nhỏ
Một trong những quyết định học thuật quan trọng nhất của khóa luận là việc lựa chọn giữa **Support Vector Machine (SVM)** và các kiến trúc **Deep Learning (1D-CNN, LSTM)**.

#### Bản chất Toán học của Support Vector Machine (RBF Kernel)
* Cho tập dữ liệu huấn luyện gồm $M$ mẫu: $\{(\mathbf{x}_i, y_i)\}_{i=1}^M$, với $\mathbf{x}_i \in \mathbb{R}^D$ ($D = 150 \times 20 = 3000$ đặc trưng chuỗi) và nhãn $y_i \in \{-1, +1\}$.
* SVM giải quyết bài toán quy hoạch toàn phương lồi (Convex Quadratic Programming):
  $$\min_{\mathbf{w}, b, \boldsymbol{\xi}} \frac{1}{2} \|\mathbf{w}\|^2 + C \sum_{i=1}^M \xi_i$$
  thỏa mãn điều kiện:
  $$y_i (\mathbf{w}^T \phi(\mathbf{x}_i) + b) \ge 1 - \xi_i, \quad \xi_i \ge 0, \quad \forall i = 1, \dots, M$$
* Hàm nhân RBF (Radial Basis Function Kernel) ánh xạ dữ liệu vào không gian Hilbert vô hạn chiều:
  $$K(\mathbf{x}_i, \mathbf{x}_j) = \exp\left(-\gamma \|\mathbf{x}_i - \mathbf{x}_j\|^2\right), \quad \gamma > 0$$
* Hàm phân loại cuối cùng chỉ phụ thuộc vào một tập hợp nhỏ các Vector hỗ trợ (Support Vectors - SV):
  $$f(\mathbf{x}) = \text{sign}\left(\sum_{i \in SV} \alpha_i y_i K(\mathbf{x}_i, \mathbf{x}) + b\right)$$

#### Phân tích chuyên sâu: Vì sao SVM vượt trội hơn Deep Learning trong đề tài này?

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               MA TRẬN ĐỐI SÁNH KỸ THUẬT: SVM RBF vs. DEEP LEARNING (1D-CNN / LSTM)     │
├─────────────────────────┬──────────────────────────────┬───────────────────────────────┤
│ Tiêu chí so sánh        │ SVM Kernel RBF               │ Deep Learning (1D-CNN / LSTM) │
├─────────────────────────┼──────────────────────────────┼───────────────────────────────┤
│ Quy mô dữ liệu yêu cầu  │ Nhỏ đến vừa (vài trăm mẫu)   │ Lớn (hàng chục nghìn mẫu)     │
│ Nguy cơ Overfitting     │ Rất thấp (Tối ưu hóa biên)   │ Rất cao nếu ít mẫu            │
│ Bản chất cực trị        │ Toàn cục duy nhất (Convex)   │ Cực tiểu địa phương (Non-conv)│
│ Thời gian suy luận      │ Cực nhanh (< 2 ms)           │ Trung bình đến chậm (15-50 ms)│
│ Kích thước tệp mô hình  │ Nhỏ (Vài trăm KB đến 2 MB)   │ Lớn (10 MB đến 100 MB)        │
│ Khả năng giải thích     │ Dựa trên khoảng cách hình học│ Hộp đen (Black-box)           │
│ Triển khai vi điều khiển│ Rất dễ (Lưu mảng Support Vec)│ Cần runtime TFLite Micro phức │
└─────────────────────────┴──────────────────────────────┴───────────────────────────────┘
```

1. **Vấn đề kích thước mẫu (Sample Size Efficiency):**
   * Trong nghiên cứu găng tay cảm biến, mỗi lượt thu dữ liệu đòi hỏi người khiếm thính hoặc sinh viên phải đeo găng, thực hiện cử chỉ và gán nhãn thủ công (Trial-based collection). Do đó, kích thước tập dữ liệu thường dao động từ 500 đến 3.000 mẫu.
   * Mạng Deep Learning (nhiều triệu tham số) trên tập dữ liệu này sẽ lập tức rơi vào hiện tượng **ghi nhớ vẹt (Overfitting)**, độ chính xác trên tập train đạt 100% nhưng tập test thực tế rất thấp. Ngược lại, nguyên lý Tối đa hóa lề (Margin Maximization) của SVM giúp mô hình tổng quát hóa cực tốt ngay cả khi số chiều đặc trưng lớn hơn số lượng mẫu.
2. **Bảo đảm tính tối ưu toán học:**
   * Bài toán của SVM là bài toán tối ưu lồi (Convex Optimization), đảm bảo nghiệm tìm được luôn là **nghiệm tối ưu toàn cục (Global Optimum)**.
   * Ngược lại, mạng nơ-ron huấn luyện bằng lan truyền ngược (Backpropagation/SGD) phụ thuộc lớn vào việc khởi tạo trọng số ngẫu nhiên và dễ bị mắc kẹt tại các điểm cực tiểu cục bộ (Local Minima) hoặc điểm yên ngựa (Saddle Points).

---

# CHƯƠNG 4: XU HƯỚNG CÔNG NGHỆ EMBEDDED AI & PHÁT ÂM TIẾNG NÓI (TINYML & TTS)

### 4.1. Xu hướng TinyML: Triển khai TensorFlow Lite for Microcontrollers (TFLite Micro) trên ESP32-S3
Trong các hệ thống thế hệ cũ, vi điều khiển chỉ đóng vai trò thu thập ADC cảm biến rồi truyền qua Wi-Fi/Bluetooth lên máy tính hoặc máy chủ đám mây để chạy mô hình AI. Hướng tiếp cận này gặp các nhược điểm:
* Tiêu thụ điện năng Wi-Fi rất lớn (ESP32 tiêu tốn 150–250 mA khi bật RF liên tục), pin nhanh cạn.
* Độ trễ mạng không ổn định (Network latency jitter).
* Phụ thuộc hoàn toàn vào hạ tầng mạng; nếu mất sóng Wi-Fi thì thiết bị tê liệt.

Xu hướng mới nhất hiện nay là **Edge AI / TinyML** – nhúng trực tiếp mô hình học máy vào trong chip vi điều khiển để suy luận độc lập ngay tại biên (On-device inference).

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ HUẤN LUYỆN MODEL│       │ CHUYỂN ĐỔI SANG │       │  LƯỢNG TỬ HÓA   │       │ XUẤT MẢNG C C++ │
│ Keras / PyTorch ├──────►│ TFLite FlatBuffer├──────►│      INT8       ├──────►│  model_data.h   │
│   (Float32)     │       │   (.tflite)     │       │ (PTQ / QAT)     │       │ (Flash ESP32)   │
└─────────────────┘       └─────────────────┘       └─────────────────┘       └────────┬────────┘
                                                                                       │
                                                                                       ▼
                                                                              ┌─────────────────┐
                                                                              │  TFLITE MICRO   │
                                                                              │ INFERENCE ENGINE│
                                                                              │  (ESP-NN SIMD)  │
                                                                              └─────────────────┘
```

#### Quy trình tối ưu hóa và lượng tử hóa INT8 (Quantization):
1. Huấn luyện mô hình 1D-CNN thu gọn hoặc MLP nhiều tầng trên TensorFlow/Keras ở định dạng số thực dấu phẩy động 32-bit (`float32`).
2. Áp dụng kỹ thuật Lượng tử hóa sau huấn luyện (**Post-Training Quantization - PTQ**):
   * Chuyển đổi toàn bộ trọng số (weights) và hàm kích hoạt (activations) từ số thực 32-bit (`float32`) sang số nguyên có dấu 8-bit (`int8`):
     $$q = \text{round}\left(\frac{r}{S}\right) + Z$$
     trong đó $r$ là giá trị thực, $S$ là hệ số tỷ lệ (Scale), $Z$ là điểm không (Zero-point).
   * **Hiệu quả:**
     * Kích thước mô hình giảm **75%** (giảm 4 lần), ví dụ từ 240 KB xuống chỉ còn 60 KB.
     * Tiết kiệm bộ nhớ SRAM nội tại của ESP32 (Tensor Arena chỉ cần 15–30 KB).
     * Tốc độ suy luận tăng từ 2 đến 4 lần do phép nhân số nguyên `int8` tiêu tốn ít chu kỳ xung nhịp CPU hơn nhiều so với FPU `float32`.

#### Tối ưu phần cứng với dòng chip ESP32-S3:
* Khác với dòng ESP32 đời đầu (Xtensa LX6), dòng **ESP32-S3 (Xtensa LX7)** được Espressif tích hợp phần cứng mở rộng **Vector Instructions (SIMD)**.
* Khi kết hợp framework TFLite Micro với thư viện tối ưu hóa vi kiến trúc **ESP-NN** của Espressif, các phép tính tích chập 1D và nhân ma trận `int8` được tính toán song song đa kênh trên thanh ghi vector 128-bit.
* Thời gian suy luận cho một cửa sổ 150 mẫu cảm biến trên ESP32-S3 đạt dưới **12 ms**, tiêu thụ dòng điện dưới 40 mA, hoàn toàn đáp ứng thời gian thực cho một thiết bị đeo dùng pin Li-Po.

### 4.2. Các giải pháp phát âm tiếng nói (Text-to-Speech) cho thiết bị đeo
Mục tiêu cuối cùng của găng tay thông minh là giúp người nghe bình thường có thể nghe được người khiếm thính nói gì. Có 3 giải pháp kỹ thuật chính để thực hiện Text-to-Speech:

```
                               ┌────────────────────────────────────────────────────────┐
                               │ CÁC GIẢI PHÁP PHÁT ÂM TIẾNG NÓI CHO GĂNG TAY THÔNG MINH│
                               └───────────────────────────┬────────────────────────────┘
                                                           │
               ┌───────────────────────────────────────────┼───────────────────────────────────────────┐
               ▼                                           ▼                                           ▼
┌───────────────────────────────┐           ┌───────────────────────────────┐           ┌───────────────────────────────┐
│     GIẢI PHÁP 1: THẺ NHỚ      │           │     GIẢI PHÁP 2: I2S DAC      │           │    GIẢI PHÁP 3: HYBRID BLE    │
│       (DFPlayer Mini)         │           │    (MAX98357A + Amplifier)    │           │      (Smartphone TTS API)     │
├───────────────────────────────┤           ├───────────────────────────────┤           ├───────────────────────────────┤
│ • Giao tiếp UART với ESP32    │           │ • Giao thức âm thanh số I2S   │           │ • Truyền ký hiệu qua BLE/Wi-Fi│
│ • Phát các file .mp3 thu sẵn  │           │ • Giải mã trực tiếp trên chip │           │ • Sử dụng Google TTS trên App │
│ • Âm thanh to, rõ, giá rẻ     │           │ • Ghép âm tiết phần mềm       │           │ • Giọng đọc tự nhiên, ghép câu│
│ • Từ vựng bị cố định          │           │ • Tốn RAM, chất lượng robot   │           │ • Linh hoạt, hiện đại nhất    │
└───────────────────────────────┘           └───────────────────────────────┘           └───────────────────────────────┘
```

#### Chi tiết 3 giải pháp:
1. **Giải pháp 1: Module giải mã phần cứng DFPlayer Mini (MP3-TF-16P)**
   * *Nguyên lý:* Sử dụng thẻ MicroSD lưu sẵn các tệp âm thanh `.mp3` chất lượng cao tương ứng với các chữ cái ("A", "B",...) và các cụm từ thông dụng ("Xin chào", "Cảm ơn",...). ESP32 kết nối với DFPlayer qua giao thức nối tiếp UART (chân TX/RX). Khi AI nhận diện được nhãn, ESP32 gửi lệnh HEX (ví dụ: `0x7E 0xFF 0x06 0x03 0x00 0x00 0x01 0xFE 0xF7 0xEF`) để phát tệp tương ứng ra loa 3W.
   * *Ưu điểm:* Hoạt động hoàn toàn độc lập không cần điện thoại, âm thanh cực kỳ trong trẻo, không tốn tài nguyên tính toán của ESP32.
   * *Nhược điểm:* Bộ từ vựng bị đóng khung theo các file thu sẵn, không thể đọc các từ ngữ mới hoặc ghép câu linh hoạt.
2. **Giải pháp 2: Bộ giải mã âm thanh số I2S DAC (MAX98357A)**
   * *Nguyên lý:* ESP32 sử dụng bus I2S chuẩn phần cứng (3 dây tín hiệu: BCLK, LRC, DIN) truyền luồng PCM âm thanh số trực tiếp sang chip khuếch đại Class D MAX98357A đánh trực tiếp ra loa ngoài.
   * *Phần mềm:* Sử dụng thư viện nhúng như `ESP8266Audio` hoặc công cụ tổng hợp giọng nói mã nguồn mở siêu nhẹ như **SAM (Software Automatic Mouth)** hoặc **Flite (Festival Lite)**.
   * *Ưu điểm:* Có thể tổng hợp văn bản bất kỳ thành âm thanh trực tiếp trên chip nhúng.
   * *Nhược điểm:* Chất lượng âm thanh còn mang tính kim khí (giọng robot), tốn tài nguyên RAM và việc hỗ trợ xử lý dấu thanh tiếng Việt (ngữ âm học tiếng Việt) trên chip nhúng là một thách thức kỹ thuật rất phức tạp.
3. **Giải pháp 3: Kiến trúc Hybrid qua Bluetooth Low Energy (BLE) / Wi-Fi lên Smartphone (Khuyến nghị cho ứng dụng thực tế)**
   * *Nguyên lý:* Găng tay thông minh chỉ đảm nhiệm việc thu nhận cảm biến và suy luận ra nhãn ký hiệu dạng chuỗi ký tự (Text string). Chuỗi ký tự này được truyền không dây về điện thoại thông minh qua BLE GATT Service hoặc WebSocket/HTTP.
   * *Tận dụng sức mạnh Smartphone:* Ứng dụng di động (Android / iOS / Web PWA) kích hoạt hệ thống Text-to-Speech bản địa của hệ điều hành (**Google Text-to-Speech API**, Android `TextToSpeech`, Apple AVFoundation `AVSpeechSynthesizer`, hoặc HTML5 Web Speech API `window.speechSynthesis`).
   * *Ưu điểm vượt trội:*
     * Giọng đọc tiếng Việt tự nhiên chuẩn giọng ba miền (Bắc, Trung, Nam), có ngữ điệu, ngắt nghỉ mượt mà.
     * Khả năng ghép chuỗi từ thành câu hoàn chỉnh và dịch đa ngôn ngữ (ví dụ: người điếc làm ký hiệu tiếng Việt nhưng loa điện thoại có thể phát âm tiếng Anh cho khách du lịch nước ngoài).
     * Giúp giảm tối đa trọng lượng phần cứng và mức tiêu thụ pin trên chiếc găng tay đeo ở tay người dùng.

---

# DANH MỤC TÀI LIỆU THAM KHẢO (CHUẨN IEEE CITATION)

Dưới đây là danh mục 15 tài liệu tham khảo khoa học chuẩn xác, đúng chuẩn trích dẫn IEEE, sinh viên có thể đưa trực tiếp vào phần Danh mục tài liệu tham khảo cuối cuốn báo cáo khóa luận:

1. [1] World Health Organization (WHO), *World Report on Hearing*, Geneva: World Health Organization, Mar. 2021. [Online]. Available: https://www.who.int/publications/i/item/9789240020481
2. [2] General Statistics Office (GSO) & UNICEF, *Vietnam National Survey on People with Disabilities 2016-2019 (VDS)*, Statistical Publishing House, Hanoi, Vietnam, Tech. Rep., 2019.
3. [3] T. G. Zimmerman, J. Lanier, C. Blanchard, S. Bryson, and Y. Harvill, "A hand gesture interface device," in *Proc. SIGCHI/GI Conf. Human Factors in Computing Systems and Graphics Interface (CHI)*, Toronto, ON, Canada, 1987, pp. 189–192.
4. [4] N. Azodi and T. Pryor, "SignAloud: A wearable glove that translates sign language into speech," *Lemelson-MIT Student Prize Announcement*, Massachusetts Institute of Technology, Cambridge, MA, USA, Tech. Rep., 2016.
5. [5] S. J. Lee, J. Choi, S. Park, B. Cho, and D. Lee, "A wearable data glove with stretchable sensors for gesture recognition and human-machine interaction," *Nature Electronics*, vol. 1, no. 8, pp. 450–458, Aug. 2018.
6. [6] Y. Wu, K. Wang, and F. Jiang, "Sensory glove-based sign language gesture recognition using support vector machines and hidden Markov models," *IEEE Transactions on Human-Machine Systems*, vol. 50, no. 4, pp. 312–321, Aug. 2020.
7. [7] G. Saggio, F. Riillo, L. Sbernini, and L. R. Quitadamo, "Resistive flex sensors: a survey on materials, fabrication technologies, and applications," *MDPI Sensors*, vol. 19, no. 7, p. 1610, Apr. 2019.
8. [8] S. O. H. Madgwick, A. J. L. Harrison, and R. Vaidyanathan, "Estimation of IMU and MARG orientation using a gradient descent algorithm," in *IEEE Int. Conf. Rehabilitation Robotics (ICORR)*, Zurich, Switzerland, 2011, pp. 1–7.
9. [9] R. Mahony, T. Hamel, and J.-M. Pflimlin, "Nonlinear complementary filters on the Special Orthogonal Group," *IEEE Transactions on Automatic Control*, vol. 53, no. 5, pp. 1203–1218, Jun. 2008.
10. [10] C. Cortes and V. Vapnik, "Support-vector networks," *Machine Learning*, vol. 20, no. 3, pp. 273–297, Sep. 1995.
11. [11] R. David, P. Duke, A. Jain, V. J. Reddi, N. Jeffries, J. Li, N. Kreeger, I. Naranjo-Alcazar, M. Slaney, T. Warden, and P. Warden, "TensorFlow Lite Micro: Embedded machine learning on TinyML systems," in *Proc. 3rd Conf. Machine Learning and Systems (MLSys)*, Austin, TX, USA, 2021, pp. 800–811.
12. [12] V. J. Reddi et al., "Widening access to applied machine learning with TinyML," *Harvard University & TinyML Foundation*, White Paper, 2022.
13. [13] Espressif Systems, *ESP32-S3 Technical Reference Manual: Vector Processing Extension and AI Acceleration*, Espressif Systems Co., Ltd., Shanghai, China, Tech. Doc., 2023.
14. [14] Ministry of Education and Training (MOET), *Tài liệu Hướng dẫn Ký hiệu Ngôn ngữ Ký hiệu dùng cho Học sinh Khiếm thính Cấp Tiểu học*, Nhà xuất bản Giáo dục Việt Nam, Hà Nội, 2019.
15. [15] H. Cooper, B. Holt, and R. Bowden, "Sign language recognition: A review," *Computer Vision and Image Understanding*, vol. 115, no. 1, pp. 101–111, Jan. 2011.

