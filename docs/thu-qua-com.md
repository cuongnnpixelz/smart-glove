# Thu 5 ngón qua USB / cổng COM

## Tự nhập từ muốn thu

Chạy trong terminal tại thư mục dự án (đóng Serial Monitor trước):

```powershell
.\chay-thu-tu-tuy-chon.cmd
```

Mặc định COM3, U01 (thư mục U1), 10 lượt mỗi từ. Hiệu chuẩn cả 5 ngón đầu phiên,
sau đó nhập từ bất kỳ, có thể có dấu: `cảm ơn` thành nhãn `CAM_ON`, file `cam_on.csv`.
Chọn `D` nếu có chuyển động, `T` nếu giữ tư thế. Mỗi lượt đếm ngược 5 giây rồi
thu 1,5 giây ở 100 Hz. Động tác động bắt đầu khi hiện BAT DAU; động tác tĩnh tạo
tư thế trước khi hết đếm ngược. ENTER lưu lượt vừa thu, R bỏ và thu lại.

Hết 10 lượt, nhập từ tiếp theo theo thứ tự tùy ý. Nhập lại cùng từ để thu thêm
10 lượt vào cùng file, giữ nguyên loại động/tĩnh đã chọn. Nhập `NONE` để thu
tư thế nghỉ/chuyển động không thuộc các nhãn. Nhập `/Q` tại menu từ để kết thúc
(chữ `Q` vẫn là một nhãn có thể thu); tại câu hỏi từng lượt, `Q` kết thúc phiên.

Mỗi lần chạy tạo thư mục phiên riêng trong `SmartSignLanguage/sequence_data_5_100hz/U1/`,
có tên chứa `TU_TUY_CHON`. Bên trong là các CSV theo từ và `imu_reference.json`.
Dữ liệu các phiên trước được giữ nguyên. Có thể đổi số lượt hoặc người thu:

```powershell
.\chay-thu-tu-tuy-chon.cmd --repetitions 20 --user-id U02 --serial-port COM3
```

Thu COM không cần Wi-Fi. Firmware **USB + Wi-Fi** trong `mophong_com` hỗ trợ cả hai:
thu bằng USB rồi trở lại Wi-Fi mà không phải nạp lại. Dùng cáp USB **có truyền dữ liệu** nối ESP32 với máy tính.
GPIO vẫn là **32, 33, 34, 35, 36 = cái, trỏ, giữa, áp út, út**.
Mỗi ngón: 3,3 V → flex → điểm GPIO → điện trở 10 kΩ → GND.
MPU6050: SDA 27 / SCL 26; LCD: SDA 21 / SCL 22 như mạch hiện tại.

## 1. Nạp firmware COM một lần

1. Dừng Python đang thu bằng Ctrl+C.
2. Arduino IDE → File → Open → **`mophong_com/mophong_com.ino`**.
3. Kiểm tra `WIFI_NAME`, `WIFI_PASSWORD`, `LOCAL_IP`, `GATEWAY`, `SUBNET` ở đầu sketch:
   dùng cấu hình mạng bạn đã dùng cho ESP32. Chọn board ESP32 hiện tại và cổng trong Tools → Port.
   Ghi lại COM, ví dụ COM5.
4. Bấm Upload, chờ hoàn tất. Ban đầu ESP32 thử nối Wi-Fi. Khi Python mở COM và bắt tay,
   LCD chuyển sang `USB COM 100 Hz` và `5 FLEX + MPU OK`; chưa có Wi-Fi vẫn thu COM được.
5. **Đóng Serial Monitor và Serial Plotter** để Python mở được cổng.

Firmware COM dùng **230400 baud**, giao thức `RAW5_100`, lấy mẫu mục tiêu 100 Hz.
Tốc độ baud là tốc độ truyền USB/UART, khác với tần số lấy mẫu 100 Hz.
Firmware tạm tắt Wi-Fi và không cập nhật LCD trong lúc thu COM để tránh chặn vòng lấy mẫu.
**Chỉ cần nạp lại một lần để cập nhật từ bản COM cũ sang bản kết hợp mới này.** Sau đó chuyển COM/Wi-Fi
không cần nạp lại. Sketch `mophong_wireless/` là lựa chọn Wi-Fi cũ; dùng `mophong_com/` cho cả hai chế độ.

## 2. Chạy chương trình

Đã có A/B/C/D: mở **`chay-thu-bang-chu-cai.cmd`** (nhấp đúp hoặc chạy `./chay-thu-bang-chu-cai.cmd`).
Chương trình dùng COM3, người U01 (thư mục U1), thu **E → F → … → Z → NONE**, 10 lượt/nhãn.
J/Z tự có hướng dẫn chuyển động; các chữ khác giữ tĩnh. File CMD dùng được khi PowerShell chặn `.ps1`.

Mở PowerShell tại `C:\Users\Admin\Downloads\newbie4`:

```powershell
.\chay-thu-com.ps1
```

Script hiện mặc định COM3 và thứ tự E đến Z rồi NONE.
Hoặc chỉ rõ cổng ngay (thay COM5 bằng cổng thực tế):

```powershell
.\chay-thu-com.ps1 -Port COM5
```

Chọn nhãn, người thu và số lượt khác nếu cần (mặc định E đến Z rồi NONE, U01, 10 lượt/nhãn):

```powershell
.\chay-thu-com.ps1 -Port COM5 -UserId U02 -Labels A,B,C,D,NONE -Repetitions 10
```

Nếu PowerShell chặn chạy script, dùng Python trực tiếp:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/collect_sequence_com.py --serial-port COM3 --user-id U01 --labels E F G H I J K L M N O P Q R S T U V W X Y Z NONE --gesture-type auto --repetitions 10
```

Chỉ liệt kê cổng, không mở thiết bị:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/collect_sequence_com.py --list-ports
```

Xem nhanh 5 cảm biến, không lưu dữ liệu:

```powershell
.\chay-thu-com.ps1 -Port COM5 -WatchFlex
```

Môi trường hiện tại đã có pyserial. Nếu cài trên máy mới, tạo môi trường Python và cài các gói dùng cho thu/train:

```powershell
python -m venv .bridge-venv
.\.bridge-venv\Scripts\python.exe -m pip install -r SmartSignLanguage/requirements.txt numpy joblib scikit-learn
```

## 3. Hiệu chuẩn rồi thu từng chữ

1. Đợi thông báo kết nối COM và `RAW5_100` gần 100 Hz.
2. Hiệu chuẩn **cả 5 ngón cùng lúc**: Enter, đếm ngược, duỗi cả bàn tay và giữ yên 3 giây;
   tiếp theo gập cả 5 ngón, gồm cả khớp ngón cái, và giữ yên 3 giây.
   Chương trình kiểm tra riêng từng kênh; nếu chưa đạt sẽ báo ngón/GPIO và yêu cầu đo lại hai tư thế.
3. Duỗi tay, đặt yên theo yêu cầu để lấy mốc MPU. Giữ yên đến khi xuất hiện nhãn đầu, ví dụ `[E 1/10]`.
4. Tại `[E 1/10]`, Enter. Trong 5 giây đếm ngược, tạo ký hiệu E và đưa tay đến tư thế muốn thu.
   Khi hiện `BAT DAU`, **giữ nguyên ký hiệu trong 1,5 giây**. Không bắt buộc đưa tay sát đầu.
   Mốc duỗi ban đầu chỉ dùng hiệu chuẩn; không phải lặp lại mốc đó ở đầu mỗi lượt.
5. Chương trình hiện nhãn, số lượt, số mẫu, Hz, ADC của cả 5 flex và mẫu MPU đầu tiên.
   Đây là số đo thật của lượt vừa thu. Tại `Da lam dung?`: Enter để lưu, R để bỏ/thu lại,
   Q để bỏ lượt hiện tại và dừng.
6. Thu đủ 10 lượt mỗi chữ rồi sang chữ tiếp theo. Khi tới **J/Z**, chuẩn bị tư thế đầu trong đếm ngược,
   chờ `BAT DAU` mới thực hiện **một lần trong 1,5 giây**, xong giữ tư thế cuối; không quay về điểm đầu trong lượt.
   Với NONE, luân phiên tư thế nghỉ và chuyển động không phải các chữ đã chọn.
7. Thu ít nhất một phiên khác đủ các nhãn sau khi tháo/đeo lại găng để đánh giá model.

Mỗi lượt được lưu gồm **150 mẫu thật**, 5 flex và MPU, cùng cấu trúc dùng bởi `chay-train-chuoi.ps1`.
Thư mục phiên: `SmartSignLanguage/sequence_data_5_100hz/U1/<ngày_giờ_VN>__<người>__<nhãn>__<mã ngắn>/`.
Các lần thu của U01 được gom dưới thư mục ngoài `U1` (U02 → `U2`), vẫn giữ riêng từng phiên bên trong.
Ví dụ: `2026-10-15_13-03-26__U01__A-B-C-D-NONE__5300e006`.
Mỗi lần chạy tạo phiên riêng, không ghi đè lần trước; mã ngắn cuối tên tránh trùng nhau.
Trong từng phiên, mỗi nhãn có một file: `a.csv`, `b.csv`, …, `z.csv`, `none.csv`;
chỉ tạo file khi có lượt của nhãn đó được xác nhận lưu. Các dòng vẫn giữ đủ 26 cột như trước.
`imu_reference.json` dùng chung cho các file của phiên, chứa hiệu chuẩn và thông tin COM.
Không tạo bảng tổng hợp hay file xem thêm. Chương trình train vẫn đọc được phiên cũ dạng `samples.csv`;
không để cả `samples.csv` và các file theo nhãn trong cùng phiên để tránh tính trùng.
Chương trình không tự lưu lượt đang thu hoặc lượt chưa xác nhận.

Mỗi dòng CSV có **26 cột**, dùng chung cho COM và Wi-Fi:

```text
timestamp,user_id,session_id,trial_id,label,flex_1,flex_2,flex_3,flex_4,flex_5,Qw,Qx,Qy,Qz,GYRx,GYRy,GYRz,ACCx,ACCy,ACCz,ACCx_body,ACCy_body,ACCz_body,ACCx_world,ACCy_world,ACCz_world
```

Nhãn do bạn chọn khi thu, được Python gắn vào **từng mẫu**, không phải ESP32 tự đoán.
Flex lưu ADC gốc; MPU lưu gia tốc (m/s²), vận tốc góc (rad/s); quaternion và gia tốc đã tách
trọng lực do Python tính. File JSON giữ mốc duỗi/gập từng ngón, gyro bias, trọng lực,
GPIO, nhãn dự kiến, người thu, phiên, tốc độ và cấu hình truyền. Không cần tạo CSV mẫu trống hay điền nhãn thủ công.

## Thu xong, dùng Wi-Fi ngay trên cùng firmware

1. Thu xong hoặc nhấn Q/Ctrl+C để thoát Python. Chương trình gửi `IDLE`, đóng COM;
   ESP32 bật Wi-Fi lại và LCD báo trạng thái kết nối. Nếu Python bị đóng đột ngột,
   firmware bật lại Wi-Fi sau khoảng **6 giây không có heartbeat**.
2. Bật đúng hotspot/router đã cấu hình. Giữ nguồn ESP32; có thể giữ cáp USB chỉ để cấp nguồn.
   Nếu rút cáp, cần nguồn khác cho ESP32. Khi khởi động lại, firmware mặc định thử nối Wi-Fi.
3. Đợi LCD `WIFI SAN SANG`. Có thể kiểm tra cổng từ PowerShell:

```powershell
Test-NetConnection 192.168.137.115 -Port 5000
```

4. Để tiếp tục **thu 5 ngón qua Wi-Fi**, chạy `chay-thu-cu-chi.ps1` như trước.
   Để train dữ liệu đã thu COM, chạy `chay-train-chuoi.ps1`.
   Firmware giữ các giao thức Wi-Fi cũ (RAW2/RAW5/RAW5_100 và lệnh hiển thị LCD),
   nhưng chương trình nhận diện phải hỗ trợ đúng model 5 ngón; chương trình/model hai ngón
   cũ không tự trở thành bộ nhận diện A/B/C/D chỉ nhờ chuyển đường truyền.

Mỗi thời điểm dùng một đường truyền. Khi bắt đầu thu COM, kết nối Python Wi-Fi hiện tại sẽ bị đóng.
Không chạy đồng thời hai chương trình để thu cùng găng.

## 4. Nếu có lỗi khi đang thu

- **Gói RAW5_100 hỏng đơn lẻ sau khi đã hiệu chuẩn:** bỏ toàn bộ gói và lượt đang thu,
  giữ kết nối, yêu cầu giữ tay yên/Enter để khởi tạo lại MPU rồi thu lại cùng lượt.
  Không sửa byte hỏng, không ghép các đoạn gói và không chèn mẫu giả.
  Nếu có 3 gói hỏng trong 10 giây, mất kết nối hoặc lỗi xảy ra trước khi khởi tạo MPU,
  chương trình dừng để kiểm tra kết nối. Thử cáp USB truyền dữ liệu khác và cổng USB trực tiếp.
- **Lượt thiếu mẫu / lệch thời gian:** bỏ lượt đó, giữ nguyên số lượt đã lưu và cho thu lại.
- **Gián đoạn timestamp trên 120 ms khi MPU đang chạy:** bỏ lượt bị lỗi và yêu cầu đặt tay yên,
  Enter để khởi tạo lại hướng MPU. Giữ yên khoảng 2,1 giây rồi thu lại cùng lượt, trong cùng phiên.
  Không hiệu chuẩn lại 5 flex. Mốc gyro/trọng lực cũ được giữ, sự kiện khởi tạo lại ghi vào `imu_recovery.jsonl`.
- **Rút USB, mất kết nối lâu, ESP32 reset hoặc timestamp quay ngược:** chương trình dừng.
  Cắm lại rồi chạy tạo phiên mới và hiệu chuẩn lại; các lượt đã lưu của phiên trước vẫn còn.
- **Lỗi trong hiệu chuẩn ban đầu:** chưa có phiên thu hoàn chỉnh; sửa nguyên nhân rồi chạy lại.

COM loại bỏ phụ thuộc Wi-Fi, không bảo đảm phần cứng luôn đạt 100 Hz. Vẫn kiểm tra timestamp thực,
giữ ngưỡng chất lượng, không chèn mẫu giả để đủ 150 mẫu. Nếu liên tục gián đoạn,
kiểm tra cáp USB, nguồn, kết nối MPU và đóng chương trình khác đang dùng COM.
Lỗi mở cổng thường do sai COM hoặc Arduino Serial Monitor/chương trình khác đang giữ cổng.
