# Chạy găng và kiểm tra nhận diện

**Trang này mô tả model/dataset cũ.** Luồng thu/train mới: [Thu dữ liệu v2](thu-du-lieu-v2.md).
`train.py` đã chuyển sang v2. Dùng `--pipeline legacy` để chạy model cũ như bên dưới.

## 1. Khởi động bản đã sửa

Mở terminal ở thư mục dự án `C:\Users\Admin\Downloads\newbie4`.
Dừng bridge cũ bằng Ctrl + C trong đúng terminal đang chạy `wifi_ai.py`, rồi chạy:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\wifi_ai.py --pipeline legacy --esp32-host 192.168.137.115
```

Nếu địa chỉ IP của ESP32 đã đổi, thay địa chỉ bằng IP được in trong Serial Monitor.
Không dùng `--demo` khi kiểm tra găng thật. Không chạy chương trình thu dữ liệu
cùng lúc vì ESP32 chỉ nhận một kết nối Python.

Trong terminal thứ hai, nếu chưa có web server:

```powershell
.\.bridge-venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1
```

Mở `http://127.0.0.1:8080/mophong1.html`, nhấn Ctrl + F5.
Chọn **AI Python · găng tay thật**, kết nối `ws://127.0.0.1:8765`.
Chờ **ESP32: có dữ liệu** và **Sẵn sàng (50/50)**. Không cần nạp lại firmware
cho thay đổi lời đọc và hàng chờ này.

## 2. Kiểm tra tiếng Anh và phát lần lượt

1. Bật **Giọng nói**, chọn giọng trong mục **Giọng Anh**, rồi bấm **Thử loa**.
   Cần nghe “Hello. Thank you very much.” Không cần cài giọng tiếng Việt.
   Web chỉ chọn giọng có ngôn ngữ tiếng Anh; không đưa chữ tiếng Việt cho giọng Anh đọc.
2. Nếu danh sách trống, bấm **Tải lại giọng** hoặc mở bằng Chrome/Edge.
   Kiểm tra âm lượng và thiết bị phát Windows nếu trình duyệt báo đã đọc xong nhưng im lặng.
3. Gập ngón giữa theo động tác đã train `XIN_CHAO`: khi AI nhận,
   web phát lại đoạn chuyển động đã ghi và đọc **Hello**.
   Gập ngón trỏ theo động tác đã train `CAM_ON_NHIEU`: đọc **Thank you very much**.
4. Thực hiện hai cử chỉ liên tiếp. Mục **Đang phát** cho biết lượt hiện tại,
   **Chờ N cử chỉ** cho biết các lượt tiếp theo. Web chờ cả chuyển động
   và lời đọc hoàn tất rồi mới phát lượt kế tiếp; dữ liệu găng vẫn tiếp tục được nhận.
5. Nếu báo **Tạm dừng**, kiểm tra giọng/loa rồi bấm **Thử lại lời đọc**.
   **Bỏ qua cử chỉ** chuyển sang lượt tiếp theo. Nếu chủ động tắt **Giọng nói**,
   web chỉ phát chuyển động. Ngắt kết nối sẽ xóa hàng chờ.
6. Khi không phát cử chỉ, tay 3D theo cảm biến trực tiếp. Chọn **Mốc 3D → Tự động**
   và kiểm tra **ADC hiện tại / Độ gập**. Nếu ngón bị đảo, đổi mục **flex1** theo
   cách gắn thực tế. Mục này chỉ đổi hình vẽ; thứ tự dây vẫn phải giống lúc train.

Đoạn phát lại là dữ liệu tay đã ghi quanh thời điểm AI xét, không phải hoạt ảnh
ký hiệu chuẩn được dựng sẵn. Chỉ hai ngón có cảm biến được đo thật.
Nếu làm nhanh hơn tốc độ phát, hàng chờ sẽ dài hơn. Cử chỉ AI chưa nhận sẽ không
được thêm vào hàng chờ.

## 3. Thử một lượt nhận diện

1. Về đúng tư thế nghỉ đã thu cho nhãn `NONE`, chờ bảng báo
   **Đã nhận tư thế nghỉ**. Chữ “Chưa nhận diện” ở kết quả chính chưa đủ để
   khẳng định AI đã nhận ra tư thế nghỉ.
2. Thực hiện đúng động tác đã dùng khi thu nhãn `XIN_CHAO`, với hướng cổ tay
   và tốc độ tương tự. AI dùng cả cảm biến uốn và MPU6050; chỉ giữ ngón gập
   có thể không giống một động tác chuyển động đã được train.
3. Quan sát nhãn thô, phần trăm và lý do. Khi AI chấp nhận nhãn, kết quả chính
   hiển thị “Xin chào” khi tới lượt; lời đọc phải là **Hello**.
4. Giữ nguyên cử chỉ sẽ không tự đọc lặp. Có thể bấm **Đọc lại kết quả**
   khi nút sáng, hoặc về nghỉ rồi làm một lượt mới.
5. Làm tương tự với `CAM_ON_NHIEU`, mỗi nhãn thử khoảng 10 lượt. Ghi lại
   số lượt đúng, nhầm nhãn và chưa chấp nhận để quyết định có cần train lại.

Khi phát một lượt, ngón 3D chạy lại đoạn dữ liệu của lượt đó; khi chờ thì theo cảm biến mới nhất.
AI xét 50 mẫu gần nhất, khoảng 2 giây
ở 25 Hz. Đây là độ dài đoạn dữ liệu, không phải độ trễ cố định 2 giây cho
mỗi lần nhận diện. AI xét lại mỗi 5 mẫu và cần 2 dự đoán liên tiếp đạt 85%.
Web hiển thị khoảng cách từ mẫu cuối AI đã xét đến mẫu cảm biến mới nhất để giúp
phân biệt kết quả chậm với nhầm nhãn. Không giảm ngưỡng tùy ý chỉ để ép đọc.

## 4. Đọc kết quả để biết cần sửa gì

| Hiện tượng | Việc cần làm |
|---|---|
| ADC không đổi khi gập | Kiểm tra cảm biến, dây nối và chân ADC. |
| ADC đổi nhưng ngón 3D sai | Kiểm tra ánh xạ flex1/flex2; dùng mốc thủ công nếu dải tự động chưa phù hợp. |
| Nhãn thô đúng nhưng dưới ngưỡng | Thu thêm các lượt đúng từ găng đang đeo; kiểm tra độ khác biệt với dữ liệu cũ. |
| Nhãn thô sai và độ tin cậy cao | Kiểm tra nhãn lúc thu, dây flex1/flex2, vị trí MPU6050 và model/scaler/encoder có cùng lần train. |
| “Đang chờ nhãn ổn định” liên tục | Làm đúng động tác đã thu; kiểm tra nhiễu và dữ liệu chuyển tiếp giữa nghỉ/cử chỉ. |
| Nhãn đúng nhưng không nghe | Xem trạng thái phát tiếng, bấm Đọc lại kết quả và Thử loa. |
| Muốn lặp cùng nhãn mà không đọc | Chờ “Đã nhận tư thế nghỉ” trước khi làm lại; NONE do thiếu tin cậy không mở lượt mới. |

## 5. Thu thêm dữ liệu nếu AI vẫn nhận sai

Code `train_legacy.py` đọc `SmartSignLanguage/dataset_gesture.csv`, còn bộ thu legacy mặc định
ghi `dataset_sentence.csv`. Thu thêm vào file mặc định sẽ **không tự cập nhật**
model đang chạy. Trước tiên thu file mới riêng để giữ dữ liệu gốc:

1. Dừng bridge bằng Ctrl + C.
2. Chạy ở thư mục dự án:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\collect_sentence_wifi.py --esp32-host 192.168.137.115 --output SmartSignLanguage\dataset_gesture_new.csv --label CAM_ON_NHIEU
```

3. Enter để bắt đầu thu, thực hiện một lượt động tác khoảng 2 giây, Enter để
   kết thúc. Chương trình in số mẫu và thời lượng đã lưu. Nghỉ giữa các lượt.
4. Nhấn `C` để đổi nhãn: thu đủ `CAM_ON_NHIEU`, `XIN_CHAO` và `NONE`.
   Mục tiêu ban đầu khoảng 30–50 lượt mỗi nhãn, qua nhiều lần tháo/đeo găng.
   `NONE` là tư thế nghỉ và các chuyển động thông thường không thuộc hai nhãn.
   Giữ nguyên thứ tự dây và cách gắn MPU6050 giữa thu và sử dụng.
5. Nhấn `Q` để kết thúc. File mới chưa được model sử dụng. Cần kiểm tra chất
   lượng, chọn dữ liệu train và giữ lại một đợt thu riêng để đánh giá trước khi
   thay bộ `gesture_model.keras`, `gesture_scaler.pkl`, `label_encoder.pkl`.

Hướng dẫn này chưa tự train hoặc thay model: cần các lượt thực hiện thật có
nhãn đúng của bạn để cải thiện nhận diện. Sửa giao diện không thể bảo đảm AI
nhận đúng một cử chỉ mà dữ liệu train chưa mô tả đầy đủ.
