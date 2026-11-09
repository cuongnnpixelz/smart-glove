# Thu dữ liệu và nhận diện v2

> Với demo chuỗi hai flex hiện tại, dùng [hướng dẫn 5 giây](demo-chuoi-5s.md):
> thu xen kẽ đúng/NONE, tính dFlex trong Python, cho phép flex hồi chưa hết.
> Phần bên dưới là luồng hiệu chuẩn/cửa sổ ngắn cho web, khác với demo chuỗi này.

Nếu chỉ muốn thu nhanh các **cử chỉ mới** bằng hai flex + MPU và giữ nguyên model cũ,
dùng hướng dẫn đơn giản: [Thu cử chỉ mới](thu-cu-chi-moi-don-gian.md).

Luồng mới cho **hai flex + MPU6050**, tham khảo cấu trúc của
[nghiên cứu ASL](https://www.nature.com/articles/s41598-022-25108-2).
Không ghép dữ liệu Figshare vào găng và không tạo số đo cho ba ngón chưa có cảm biến.

## Dữ liệu được lưu

```csv
timestamp,user_id,session_id,trial_id,label,flex_1,flex_2,Qw,Qx,Qy,Qz,GYRx,GYRy,GYRz,ACCx,ACCy,ACCz,ACCx_body,ACCy_body,ACCz_body,ACCx_world,ACCy_world,ACCz_world
```

- Flex: ADC 12-bit, trung bình ba lần đọc. **CSV không bị đổi thành số 0–1**.
- Timestamp: mili giây từ mốc khởi động firmware, không phải Unix giây; không reset giữa các lượt.
- GYR: rad/s gốc. ACC: m/s², còn trọng lực.
- Q: quaternion Hamilton `[w,x,y,z]`, chuyển từ trục cảm biến sang hệ trục cục bộ.
- ACC_body: gia tốc đã trừ trọng lực trong trục cảm biến. ACC_world: cùng gia tốc đó xoay sang hệ trục cục bộ.
- Không có dFlex trong CSV mới. ID và nhãn không đưa vào model.

Mỗi phiên có `calibration.json`: mốc duỗi/gập, gyro bias, độ lớn gia tốc nghỉ,
ánh xạ ngón, đơn vị và phiên bản xử lý. Python tính flex chuẩn hóa khi tạo đầu vào AI,
rồi dùng scaler chỉ fit trên train. Công thức hoạt động cả khi ADC giảm lúc gập.

Giữ **25 Hz**, mục tiêu 40 ms/mẫu. Kiểm tra chấp nhận trung bình 22–28 Hz,
khoảng trống tối đa 120 ms; đây là ngưỡng của dự án, không phải chuẩn công nghiệp.
Thu mỗi lượt **2,4 giây**. Train và nhận diện cùng lấy cửa sổ 50 điểm cách nhau
40 ms (khoảng 2 giây), trượt khoảng 200 ms, nội suy theo timestamp.
Không ép câu dài 8–10 giây vào cửa sổ này.

## 1. Nạp firmware

1. Dừng Python đang kết nối găng.
2. Mở `mophong_wireless/mophong_wireless.ino` bằng Arduino IDE, chọn đúng board/cổng và Upload.
3. Xem IP găng trong Serial Monitor. Chỉ chạy một chương trình TCP kết nối găng cùng lúc.

Firmware hỗ trợ lệnh `RAW2` để gửi timestamp + 2 ADC + 6 kênh IMU, không tính/truyền
dFlex ở chế độ mới. Client legacy vẫn dùng DATA v1. Lịch lấy mẫu giữ mốc 40 ms,
bỏ chu kỳ quá trễ thay vì tạo mẫu bù giả. Nhịp thực tế vẫn phải kiểm tra qua timestamp.

## 2. Hiệu chuẩn và thu một phiên

Mở terminal tại thư mục dự án:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\collect_v2.py --user-id U01 --esp32-host 192.168.137.115
```

Thay IP nếu khác. Mặc định flex1 gắn ngón trỏ; nếu gắn ngón giữa, thêm
`--flex1-finger Middle` và giữ đúng ánh xạ ở mọi phiên.

Làm theo ba bước trên terminal:

1. Duỗi hai ngón, chờ ổn định, Enter; sau đếm ngược giữ yên 2 giây.
2. Gập hai ngón, Enter; sau đếm ngược giữ yên 2 giây.
3. Duỗi lại và giữ yên cả bàn tay, Enter để đo gyro bias và kiểm tra hồi về mốc.

Nếu báo dải quá nhỏ, không ổn định hoặc flex chưa hồi về mốc, kiểm tra cách gắn/cảm biến
rồi chạy lại. Không ép mốc để che lỗi hồi chậm. Sau đó giữ yên thêm 2,4 giây khởi tạo IMU.

Menu thu:

- `1`: XIN_CHAO; `2`: CAM_ON_NHIEU; `3`: NONE.
- Enter: đếm ngược 3–2–1, tự thu 2,4 giây rồi kết thúc.
- `Q`: dừng.

Mỗi lượt thực hiện đúng một động tác. Bắt đầu khi hiện BAT DAU, hoàn tất trong cửa sổ.
Nghỉ giữa các lượt và kiểm tra flex đã hồi. Thu NONE cho nghỉ và các chuyển động thông
thường không thuộc hai cử chỉ; không gán NONE cho một lượt làm đúng cử chỉ.
Sau mỗi lượt xem số mẫu, Hz, khoảng cách mẫu lớn nhất. Lượt lỗi không được lưu.
Reset/mất kết nối thì tạo phiên mới, không nối dữ liệu tùy ý.

Các file được tạo **khi thu thật**:

```text
SmartSignLanguage/data_v2/<ma-phien>/calibration.json
SmartSignLanguage/data_v2/<ma-phien>/samples.csv
SmartSignLanguage/calibration/current.json
```

Không có dữ liệu giả điền sẵn. `current.json` là lần hiệu chuẩn gần nhất;
mốc riêng từng phiên vẫn được giữ. Mẫu trước khi bộ lọc sẵn sàng không lưu thành trial.

## 3. Thu nhiều phiên và kiểm tra

Tối thiểu theo hướng dẫn: **3 phiên độc lập, mỗi phiên đủ 3 nhãn, 10 lượt mỗi nhãn**
(90 lượt). Nên thu từ 5 phiên qua các lần tháo/đeo, ngày khác nhau. Chỉ đổi tên phiên
trên cùng một lượt thu không tạo tính độc lập. Nếu nhiều người, đổi `--user-id`.
Giữ thứ tự dây, vị trí IMU và định nghĩa động tác thống nhất.

Kiểm tra CSV, nhịp mẫu, quaternion/gia tốc và cách chia phiên trước khi train:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\train.py --check-only
```

Chia train/validation/test theo phiên. Với từ ba người đủ dữ liệu, dùng
`--group-by user` để đánh giá trên người chưa xuất hiện trong train.
Không chia các cửa sổ chồng lấn của cùng lượt sang nhiều tập.

## 4. Train

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\train.py
```

Mặc định 11 đầu vào: 2 flex chuẩn hóa, 3 gyro đã trừ bias, 3 gia tốc gốc và
3 gia tốc tuyến tính body. Quaternion/world vẫn lưu để phân tích, chưa làm đầu vào
model vì không có hướng tuyệt đối. Bộ xử lý lúc train và nhận diện dùng chung.

Đầu ra `SmartSignLanguage/models/v2/`: model, scaler, encoder, manifest và report.
Manifest ghi thứ tự đặc trưng, phiên bản xử lý, tần số và hash file để tránh trộn model.
Report ghi các phiên tách riêng, hash nguồn, điểm theo lượt và ma trận nhầm lẫn.
Nếu output đã tồn tại, dùng tên mới, không ghi đè:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\train.py --output SmartSignLanguage\models\v2_lan2
```

So sánh bộ 8 đầu vào với cùng dữ liệu/cách chia:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\train.py --features base8 --output SmartSignLanguage\models\v2_base8
```

Dùng validation để điều chỉnh, giữ một phiên/người khác để đánh giá cuối và thử chuỗi
liên tục trên găng. Không coi unit test hay điểm dữ liệu mô phỏng là độ chính xác thật.

## 5. Chạy web

Nếu tháo/đeo lại, hiệu chuẩn cho phiên sử dụng:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\collect_v2.py --user-id U01 --calibrate-only
```

Thêm IP/ánh xạ ngón như lúc thu nếu khác mặc định. Sau đó:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\wifi_ai.py --pipeline v2 --esp32-host 192.168.137.115
```

Nếu output train khác, thêm `--model-dir SmartSignLanguage\models\v2_lan2`.
Thiếu calibration/model v2 thì báo rõ, không âm thầm dùng model cũ.
Giữ yên lúc vừa kết nối để khởi tạo IMU; đợi trạng thái sẵn sàng.

Terminal thứ hai:

```powershell
.\.bridge-venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1
```

Mở `http://127.0.0.1:8080/mophong1.html`, Ctrl+F5, kết nối `ws://127.0.0.1:8765`.
Web dùng mốc Python cho tay 3D, khóa mốc riêng trên web và dùng quaternion Python.
Lời đọc vẫn Hello/Thank you very much; xong hình và tiếng mới tới lượt tiếp theo.

## Giới hạn và bản cũ

Bộ lọc là quaternion complementary filter hiệu chỉnh theo trọng lực, không phải
bản sao DMP của tác giả. World +Z theo gia tốc nghỉ; yaw tương đối có thể trôi vì
không có từ kế. Không coi đây là hướng Bắc hay vị trí tuyệt đối.
Gyro bias và độ lớn gia tốc nghỉ không thay thế hiệu chuẩn accelerometer nhiều tư thế.
Phải kiểm tra hiệu quả trên găng thực tế trước khi kết luận tốt hơn.

CSV/model cũ giữ nguyên; chương trình train trước đây được lưu ở `train_legacy.py`.
Các script `convert_int8.py`, `test_ai.py`, `tflite_to_header.py` thuộc bộ legacy;
không dùng chúng để chuyển/nạp model v2. V2 hiện suy luận trên Python/laptop.
Chạy lại model cũ khi chưa thu đủ v2:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\wifi_ai.py --pipeline legacy
```

Trạng thái ghi LEGACY, mốc v2 không áp dụng lên model cũ. Không dùng các bộ thu cũ
`collect_data.py`/`collect_sentence_wifi.py` để tạo v2. Không tự đoán mốc, quaternion
hay timestamp để chuyển dữ liệu cũ thành mới.

## Kiểm tra phần mềm

```powershell
.\.bridge-venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
.\.bridge-venv\Scripts\python.exe tests/v2_training_smoke.py
.\.bridge-venv\Scripts\python.exe tests/browser_smoke.py
```

Smoke training dùng mẫu tổng hợp trong thư mục tạm `.runtime`, xóa khi xong;
không tạo model/dataset sản xuất. Người dùng cần Upload firmware qua Arduino IDE.
