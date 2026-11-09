# Nhận diện A/B/C/D/NONE liên tục bằng Wi-Fi

Chương trình này dùng **model 5 ngón, 100 Hz, cửa sổ 1,5 giây** vừa train.
Nó tự cập nhật kết quả, không cần Enter cho mỗi lượt hoặc duỗi tay về nghỉ giữa các chữ.
Model hai ngón và chương trình `predict_continuous.py` cũ không dùng cho luồng này.

## Chạy

1. Dừng chương trình thu COM và đóng Serial Monitor/Plotter. Giữ nguồn ESP32, bật đúng hotspot.
2. Để kết quả hiện trên **LCD**, nạp bản mới `mophong_com/mophong_com.ino` một lần.
   Bản này bổ sung lệnh hiển thị chữ và cập nhật LCD ở tác vụ riêng, tránh chặn vòng đọc cảm biến.
   Firmware USB + Wi-Fi đã nạp trước đó vẫn gửi dữ liệu cho kết quả trên Terminal, nhưng chưa hiểu lệnh LCD mới.
3. Chờ ESP32 kết nối Wi-Fi. Trong Terminal tại thư mục `newbie4`, chạy:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/predict_continuous_5.py
```

Hoặc nhấp đúp `chay-nhan-dien-5-ngon.cmd`. File CMD không cần thay đổi chính sách chạy PowerShell.

4. Giữ tay yên khoảng **5 giây** để tự lấy lại mốc MPU.
5. Khi hiện `SAN SANG`, tạo A, giữ khoảng 2 giây; rồi đổi sang B/C/D.
   Kết quả được in lặp lại trên Terminal và gửi tới LCD. Tư thế nghỉ có thể được phân loại NONE.
6. Nhấn **Ctrl+C** để dừng.

Không cần nạp model vào ESP32: Python chạy model trên máy tính, ESP32 gửi cảm biến và nhận chữ để hiển thị.
Máy tính cần duy trì kết nối với mạng của ESP32 và chương trình Python phải đang chạy.
IP mặc định `192.168.137.115`, TCP 5000. Nếu IP khác, thêm `--esp32-host <IP>`.

## Mốc flex và model

Chương trình tự chọn model hoàn chỉnh mới nhất trong `models/sequence_5_100hz_*` và
mốc flex của phiên thu có CSV mới nhất. Các đường dẫn được in khi bắt đầu.
Mặc định này phù hợp để thử ngay khi **vẫn đeo găng như lúc thu**. Mốc MPU được đo lại ở mỗi kết nối.

Nếu đã tháo/đeo lại găng hoặc dịch chuyển cảm biến, chạy:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/predict_continuous_5.py --recalibrate
```

Lúc này hiệu chuẩn cả 5 ngón cùng lúc: duỗi cả bàn tay, rồi gập cả 5 ngón; sau đó nhận diện tự chạy liên tục.
Mốc mới chỉ dùng trong lần chạy này, được giữ khi tự kết nối lại; không ghi đè phiên thu/train.
Có thể chỉ định mốc bằng `--reference <đường dẫn imu_reference.json>` hoặc model bằng `--model <thư mục model>`.

## Cách cập nhật kết quả

- Lấy **150 mẫu thật mới nhất**, đúng tiền xử lý lúc train.
- Xét lại mỗi **0,25 giây** dữ liệu cảm biến, yêu cầu 2 dự đoán liên tiếp cùng nhãn trước khi hiện chữ mới.
- Do cửa sổ dài 1,5 giây, khi đổi chữ cần giữ khoảng **2 giây** cho kết quả ổn định.
  Cập nhật mỗi 0,25 giây không có nghĩa độ trễ nhận diện chỉ 0,25 giây.
- NONE là một nhãn đã học. Chương trình không gán xác suất phần trăm giả cho SVM;
  cử chỉ lạ vẫn có thể bị nhận nhầm thành A/B/C/D nếu dữ liệu NONE còn ít.
- Thiếu mẫu, ADC sát biên hoặc thời gian không đạt: bỏ cửa sổ, hiện trạng thái chờ/lỗi.
  Mất kết nối hoặc gián đoạn lớn: tự nối lại và yêu cầu giữ yên để lấy lại mốc MPU.

Kết quả test 100% của model đầu tiên chỉ tính trên 13 lượt cùng phiên thu.
Khả năng nhận diện liên tục và độ chính xác sau khi đeo lại găng cần kiểm tra trên phần cứng thật.
