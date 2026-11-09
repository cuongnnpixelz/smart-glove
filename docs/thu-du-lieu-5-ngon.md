# Thu dữ liệu và huấn luyện găng tay 5 ngón

**Muốn thu bằng cáp USB, không cần Wi-Fi:** dùng firmware `mophong_com/mophong_com.ino`
và `chay-thu-com.ps1`. Xem [hướng dẫn COM từng bước](thu-qua-com.md).
Phần nạp/kết nối bên dưới dành cho firmware Wi-Fi; định dạng dữ liệu và train dùng chung.

Firmware: `mophong_wireless/mophong_wireless.ino`. Thứ tự mặc định:

| Kênh CSV | Ngón | GPIO ESP32 |
|---|---|---|
| flex_1 | Cái | 32 |
| flex_2 | Trỏ | 33 |
| flex_3 | Giữa | 34 |
| flex_4 | Áp út | 35 |
| flex_5 | Út | 36 (VP) |

Mạch người dùng xác nhận: **3,3 V và điện trở 10 kΩ xuống GND**, riêng cho mỗi ngón:

```text
3V3 ── flex ──┬── GPIO tương ứng
             │
            10 kΩ
             │
            GND
```

Khi điện trở flex tăng do uốn, điện áp/ADC giảm:
`V_GPIO = 3,3 × 10000 / (R_flex + 10000)`.
Ví dụ lý tưởng, flex 25 kΩ cho khoảng 0,94 V; 50 kΩ cho khoảng 0,55 V.
Đây là ví dụ tính mạch, không phải thông số đo từ cảm biến trong ảnh.
Nhãn Spectra Symbol trên ảnh chưa xác định được mã/điện trở: hãng có nhiều phiên bản
[10 kΩ và 25 kΩ](https://store.spectrasymbol.com/en-au/products/flex-sensor).
Giữ điện trở 10 kΩ nếu số đo đủ biên độ và ổn định. Không lấy mốc ADC của dataset
dùng 100 kΩ áp vào găng này, không nhân ADC với 10 để "quy đổi".

Dùng chung GND, không cấp 5 V vào điểm đo. GPIO 34/35/36 chỉ hỗ trợ đầu vào,
không có điện trở kéo nội; cần điện trở ngoài. Các chân đã chọn thuộc ADC1.
Xem [tài liệu GPIO Espressif](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html).

LCD vẫn SDA/SCL 21/22; MPU6050 vẫn SDA/SCL 27/26. ADC 12 bit, trung bình 3 lần đọc,
attenuation 11 dB. Luồng thu mới yêu cầu **100 Hz**; MPU đặt **±2 g, ±250°/s**,
DLPF 21 Hz, bộ chia cập nhật MPU 100 Hz.

## Nạp và thu dữ liệu

1. Mở sketch chính trong Arduino IDE, sửa Wi-Fi/IP, chọn board/cổng và Upload.
   Serial Monitor 115200 baud hiển thị IP. Không nạp bản trong `firmware_archive`.
2. Dừng chương trình Python khác đang kết nối ESP32 (chỉ một TCP client).
3. Kiểm tra cảm biến/hiệu chuẩn trước bằng lệnh:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/collect_sequence_5.py --user-id U01 --calibrate-only
```

Thay `--esp32-host` nếu IP khác mặc định `192.168.137.115`.
Đợi `RAW5_100` và số Hz đo từ timestamp. Chương trình hiệu chuẩn riêng từng ngón:
duỗi ngón được chỉ định rồi gập ngón đó thoải mái, mỗi tư thế giữ 3 giây
(bỏ 1 giây đầu để ổn định, đo 2 giây cuối). Ngón chưa đạt được thử lại riêng,
giữ kết quả các ngón đã đạt. Cuối cùng duỗi/giữ yên để lấy mốc và khởi tạo MPU.
Chương trình in thay đổi cả 5 kênh để giúp phát hiện nhầm GPIO, cùng ADC
duỗi/gập, biên độ và độ dao động cho từng ngón. Điều kiện mới áp dụng cho cả
thu và train: biên độ giảm ít nhất **15 ADC**, khoảng P5 của tư thế duỗi cao hơn
P95 của tư thế gập ít nhất **5 ADC**, và độ trôi trung vị giữa 1/4 đầu và 1/4 cuối
mỗi lần giữ không quá `max(5 ADC, 20% biên độ)`.
Không còn yêu cầu cứng 60 ADC và gấp 6 lần độ dao động. Tín hiệu nhỏ vẫn có thể
đạt nếu hai tư thế tách biệt, ổn định. Đây là ngưỡng sàng lọc của phần mềm,
không bảo đảm độ chính xác phân loại hoặc chẩn đoán phần cứng.
ADC gần 0/4095, chiều ngược, khoảng đo chồng lấn hoặc tư thế còn trôi bị từ chối
với lý do cụ thể. Mốc hiệu chuẩn mới lưu thêm phân vị và độ trôi trong phiên bản v2;
train vẫn đọc được mốc v1 đã đạt điều kiện cũ. Không cần nạp lại ESP32;
dừng Python và chạy lại để dùng điều kiện mới.

Nếu muốn xem cảm biến trực tiếp trước, dừng collector bằng Ctrl+C rồi chạy:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/collect_sequence_5.py --user-id U01 --watch-flex
```

Chế độ này không hiệu chuẩn và không ghi dataset. Mỗi dòng hiển thị ADC trung vị
và khoảng `[P5..P95]` của cả 5 ngón trong 0,4 giây. Giữ yên vài giây, gập riêng
ngón cái rồi giữ yên, sau đó duỗi lại; quan sát F1 có thay đổi lặp lại được không.
Độ rộng P95−P5 là dao động đo được, không phải ±nhiễu hay bằng chứng cảm biến hỏng.
Nếu đang cử động, khoảng này còn bao gồm chính chuyển động đó. Ctrl+C để thoát.
Sau khi cập nhật Python, phải dừng và chạy lại chương trình đang mở để nhận mã mới.

4. Chạy `chay-thu-cu-chi.ps1` hoặc:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/collect_sequence_5.py --user-id U01 --labels A B C D NONE --repetitions 10
```

Mỗi phiên **hiệu chuẩn mới**; phiên `--calibrate-only` chỉ dùng kiểm tra, không
tự tái sử dụng mốc khi đã tháo/đeo lại găng.
Chương trình lần lượt thu 10 lượt hợp lệ mỗi nhãn:
Enter → đếm ngược **5 giây** → thu **150 mẫu thật, khoảng 1,5 giây** → Enter lưu,
`R` bỏ và thử lại, `Q` bỏ lượt hiện tại và kết thúc. Lượt bỏ không tính vào 10 lượt.

Với ký hiệu tĩnh A/B/C/D, học đúng tư thế ASL, tạo tư thế trước khi hết đếm ngược
và giữ trong lúc thu. Không duỗi tay 0,5 giây đầu như luồng chuỗi cũ.
Với cử chỉ động, thực hiện trọn một lần khi báo bắt đầu; thêm `--gesture-type dynamic`
để ghi rõ loại phiên. `NONE` gồm nghỉ và chuyển động không thuộc các nhãn đã chọn.
Đây là lớp bổ sung của dự án để học trạng thái khác, không phải một chữ cái ASL.
`--label A` chỉ thu riêng A; nên dùng `--labels` để mỗi phiên có đủ các nhãn.

Mỗi phiên cần có đủ các nhãn và `NONE` (nghỉ, chuyển động khác, sai ngón/sai thứ tự).
Thu ít nhất 2 phiên độc lập, khuyến nghị 3 phiên trở lên; mỗi nhãn ít nhất 4 trial
tổng cộng để chương trình có thể train. Đây là ngưỡng tối thiểu của phần mềm,
không bảo đảm độ chính xác. Giữ thứ tự ngón và cách đeo nhất quán.

Mỗi lần chạy tạo `SmartSignLanguage/sequence_data_5_100hz/<session>/` mới:

- `samples.csv`: timestamp, người/phiên/trial/nhãn, ADC đủ 5 ngón, quaternion,
  gyro, gia tốc và gia tốc đã bỏ trọng lực trong hệ tay/hệ thế giới cục bộ.
- `imu_reference.json`: mốc MPU, mốc flex từng ngón, sơ đồ 10 kΩ/3,3 V,
  thứ tự ngón/GPIO, nhãn, số lần lặp, cấu hình và danh sách cột.

Trial thiếu kênh, ADC sát biên, MPU gần bão hòa hoặc sai nhịp bị từ chối.
Chỉ lấy mẫu sau marker BEGIN; không lấy dữ liệu cũ trong lúc đếm ngược.
Yêu cầu 150 mẫu, tốc độ đo 95–105 Hz, khoảng cách hai mẫu tối đa 20 ms và
chênh timestamp đầu/cuối 1490–1510 ms. 150 mẫu cách nhau 10 ms có 149 khoảng,
nên chênh timestamp lý tưởng là 1490 ms, không phải 1500 ms.
Nếu kết nối lỗi, các trial đã lưu vẫn còn; chạy lại để tạo phiên và hiệu chuẩn mới.
ADC luôn lưu nguyên gốc; không tự thêm mẫu vào CSV để che mất dữ liệu.

## Huấn luyện

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/train_sequence_5.py --check-only
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/train_sequence_5.py
```

Hoặc chạy `chay-train-chuoi.ps1`. Model mới nằm trong
`SmartSignLanguage/models/sequence_5_100hz_<thời điểm>_<id>/`, gồm `model.joblib`,
`manifest.json`, `report.json`. Không ghi đè model cũ.

SVM dùng 19 đặc trưng mỗi bước trên lưới 150 bước/1,5 giây: 5 flex chuẩn hóa
bằng mốc duỗi/gập của phiên, hướng trọng lực trong hệ tay (3), gyro trừ bias (3),
gia tốc bỏ trọng lực hệ tay (3), tốc độ biến thiên 5 flex.
Không trừ tư thế đầu mỗi lượt vì làm mất thông tin ký hiệu tĩnh.
Lọc median 5 mẫu cho flex; dữ liệu CSV gốc không bị sửa.
Scaler chỉ fit trên tập train. Mặc định yêu cầu tách phiên
train/test; `--allow-trial-split` chỉ kiểm tra sơ bộ khi thiếu phiên.
Đọc `report.json` để đánh giá kết quả.

Dữ liệu/model hai ngón và bản 5 ngón 25 Hz ở thư mục cũ, không trộn vào luồng này. Web và chương trình
nhận diện hiện tại chưa được nâng cấp để sử dụng model 5 ngón.

## Mức tương đồng với bộ dữ liệu tham khảo

Nhịp mục tiêu 100 Hz, cửa sổ 1,5 giây, đếm ngược 5 giây và 10 lần lặp theo
[mô tả Figshare](https://figshare.com/articles/dataset/ASL-Sensor-Dataglove-Dataset_zip/20031017).
Đây vẫn là bộ dữ liệu riêng: điện trở 10 kΩ, hiệu chuẩn flex riêng, truyền Wi-Fi,
quaternion/gia tốc suy ra từ bộ lọc Python. Bài báo dùng 100 kΩ, USB và quaternion
từ DMP. Không tuyên bố header/thang đo/hệ tọa độ giống hoàn toàn ZIP gốc và
không nạp thẳng model của dataset đó cho găng này.

## Giao thức

Mặc định firmware gửi:

```text
DATA5,time_ms,flex1,flex2,flex3,flex4,flex5,dFlex1,dFlex2,dFlex3,dFlex4,dFlex5,dFlex1Avg,dFlex2Avg,dFlex3Avg,dFlex4Avg,dFlex5Avg,ax,ay,az,gx,gy,gz
```

Collector mới gửi `RAW5_100\n`, firmware chuyển sang 10 ms/mẫu:

```text
RAW5_100,time_ms,flex1,flex2,flex3,flex4,flex5,ax,ay,az,gx,gy,gz
```

Gia tốc m/s², gyro rad/s, thời gian mili giây từ lúc khởi động.
START/STOP, BEGIN/END và điều khiển LCD giữ nguyên.
Mặc định DATA5 và các lệnh RAW5/RAW2 cũ vẫn ở 25 Hz; collector mới sẽ từ chối
firmware chưa hỗ trợ RAW5_100. MPU dùng chung cấu hình ±2 g/±250°/s mới.
`RAW2\n` vẫn trả hai kênh đầu; theo cách gắn mới là cái/trỏ,
không tương đương trỏ/giữa của găng cũ. Client chỉ hiểu DATA cũ cần cập nhật parser
hoặc dùng firmware cũ; không đổi tiền tố DATA5 thành DATA.
