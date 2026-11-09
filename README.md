# Smart Glove — ESP32, AI Python và bàn tay 3D

**Thu tiếp bảng chữ cái từ E:** mở `chay-thu-bang-chu-cai.cmd` (COM3, U01).
Thứ tự E đến Z rồi NONE, J/Z tự hướng dẫn chuyển động. Dữ liệu lưu theo
`sequence_data_5_100hz/U1/<phiên>/a.csv, b.csv, …` và một `imu_reference.json` dùng chung cho phiên.

**Nhận diện 5 ngón liên tục qua Wi-Fi:** chạy `chay-nhan-dien-5-ngon.cmd` hoặc
`.\.bridge-venv\Scripts\python.exe SmartSignLanguage/predict_continuous_5.py`.
Tự chọn model 5 ngón mới nhất, cửa sổ 1,5 giây, cập nhật mỗi 0,25 giây, không Enter từng lượt.
Xem [hướng dẫn nhận diện 5 ngón liên tục và LCD](docs/nhan-dien-5-ngon-lien-tuc.md).

**Một firmware cho USB / COM và Wi-Fi:** nạp `mophong_com/mophong_com.ino`, đóng Serial Monitor,
rồi chạy `.\chay-thu-com.ps1` (hoặc thêm `-Port COM5` với cổng thực tế).
Thu 5 ngón + MPU ở 100 Hz, 150 mẫu/lượt; lỗi gián đoạn ngắn có thể khởi tạo lại
hướng MPU và thử lại lượt đó mà vẫn giữ các lượt đã lưu.
CSV có đủ 5 flex, MPU, nhãn, người thu, phiên và lượt. Thoát thu COM thì firmware
tự nối lại Wi-Fi, không cần nạp lại; kiểm tra cấu hình Wi-Fi ở đầu sketch.
Xem [hướng dẫn thu qua COM](docs/thu-qua-com.md).

**Bản 5 ngón (13/10/2026):** firmware chính dùng GPIO **32, 33, 34, 35, 36**
tương ứng **cái, trỏ, giữa, áp út, út**. Chạy `chay-thu-cu-chi.ps1` để thu đủ
5 cảm biến với **10 kΩ xuống GND, nguồn 3,3 V**, hiệu chuẩn duỗi/gập từng phiên,
**100 Hz, 1,5 giây, 10 lượt/nhãn A/B/C/D/NONE**. Chạy `chay-train-chuoi.ps1`
để train model riêng. Dữ liệu mới ở `SmartSignLanguage/sequence_data_5_100hz/`. Xem
[hướng dẫn đấu dây, thu và train 5 ngón](docs/thu-du-lieu-5-ngon.md).
Web/nhận diện bên dưới vẫn là luồng hai ngón cũ, chưa dùng model 5 ngón.

**Sử dụng liên tục, không bấm Enter:** chạy `chay-nhan-dien-chuoi.ps1` hoặc
`predict_continuous.py`. Xem [cách nạp firmware và sử dụng LCD](docs/nhan-dien-lien-tuc.md).
Thu dữ liệu vẫn dùng chương trình riêng, cả hai dùng chung một firmware ESP32.

**Demo hiện tại: Python + ESP32, hai flex, chuỗi 5 giây:**
[Hướng dẫn thu, train và kiểm tra](docs/demo-chuoi-5s.md).
Chạy lần lượt `chay-thu-cu-chi.ps1` (3 phiên), `chay-train-chuoi.ps1`,
`chay-nhan-dien-chuoi.ps1`. Có dFlex trong xử lý Python; giữ nguyên ADC trong CSV,
không cần nạp lại firmware RAW2 đang chạy. Các luồng web bên dưới vẫn được giữ.

**Đã dọn để thu lại từ đầu ngày 08/10/2026:** dữ liệu thu cũ, model đã train,
scaler/encoder, báo cáo flex và file tạm đã được xóa theo yêu cầu.
`sequence_data_v2/` và `models/` hiện bắt đầu trống. Giữ mã nguồn web/ESP32,
môi trường Python và các module dùng chung; cần thu và train trước khi nhận diện.

**Luồng mới:** [Thu dữ liệu và nhận diện v2](docs/thu-du-lieu-v2.md).
Thu riêng các nhãn mới theo cách đơn giản: [hai flex + MPU](docs/thu-cu-chi-moi-don-gian.md).
`train.py` hiện dùng dữ liệu theo phiên, hiệu chuẩn riêng và cửa sổ theo timestamp.
CLI `wifi_ai.py` mặc định v2: cần nạp firmware, hiệu chuẩn và thu thật để train model mới.
Thêm `--pipeline legacy` nếu dùng model cũ trong các hướng dẫn bên dưới.
Báo cáo [kiểm tra dữ liệu cũ](docs/kiem-tra-du-lieu-cu.md) chỉ còn giá trị lịch sử;
các CSV/model được nhắc trong báo cáo đã được dọn.

Luồng dùng chung của hai người:

```text
ESP32 (TCP :5000) <-> wifi_ai.py (AI + WebSocket :8765) -> Web 3D
                       |
                       +-> kết quả AI trở lại LCD ESP32
```

Web nhận dữ liệu cảm biến thật để điều khiển bàn tay và nhận kết quả từ AI Python.
Mặc định là **AI Python**. K-NN trên trình duyệt và dữ liệu giả lập có chế độ riêng.
Chỉ Python kết nối trực tiếp đến TCP ESP32; web kết nối đến Python.

## 1. Chuẩn bị Python

Chạy PowerShell ở thư mục có `mophong1.html`:

```powershell
python -m venv --system-site-packages .bridge-venv
.\.bridge-venv\Scripts\python.exe -m pip install -r SmartSignLanguage/requirements.txt
```

`--system-site-packages` dùng lại TensorFlow và các thư viện AI đã cài trên máy.
Các lệnh bên dưới gọi Python của môi trường này trực tiếp, không cần Activate.ps1.
Không chạy lệnh tạo lại môi trường nếu `.bridge-venv` đã sẵn sàng.

## 2. Thử giao diện khi chưa nối găng tay

Terminal thứ nhất:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/wifi_ai.py --demo
```

Terminal thứ hai, cũng ở thư mục dự án:

```powershell
python -m http.server 8080 --bind 127.0.0.1
```

Mở **http://localhost:8080/mophong1.html**, giữ nguồn **AI Python**, địa chỉ
**ws://localhost:8765**, rồi bấm **Kết nối**. Giao diện ghi rõ dữ liệu demo;
nhãn và confidence trong chế độ này là giả lập, không phải đánh giá mô hình.
Demo không cần nạp TensorFlow hay kết nối ESP32.

Máy chưa có thư viện AI cần cài thêm trước khi dùng cảm biến thật:

```powershell
.\.bridge-venv\Scripts\python.exe -m pip install -r SmartSignLanguage/requirements-ai.txt
```

## 3. Chạy với ESP32 thật

1. Trong Arduino IDE, mở **mophong_wireless/mophong_wireless.ino**. Cấu hình Wi-Fi
   cho mạng thực tế và kiểm tra địa chỉ IP trong Serial Monitor (115200 baud).
   Bản chính dùng TCP cổng **5000**. Cài board ESP32 và thư viện
   `Adafruit MPU6050`, `Adafruit Unified Sensor`, `LiquidCrystal I2C` nếu chưa có.
2. Nạp firmware. Dùng hai cảm biến uốn ở GPIO **32/33**; LCD ở SDA/SCL **21/22**;
   MPU6050 ở SDA/SCL **27/26**. Giữ nguyên cách đấu dây của mô hình hiện tại.
3. Dừng bridge demo bằng Ctrl+C, rồi chạy (thay IP bằng IP ESP32 thực tế):

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/wifi_ai.py --pipeline legacy --esp32-host 192.168.137.115
```

4. Giữ HTTP server ở terminal thứ hai và kết nối trên web như bước 2.
5. Chờ đủ **50 mẫu**; tại 25 Hz cần khoảng **2 giây** cho cửa sổ đầu tiên.
   AI dự đoán lại mỗi 5 mẫu và yêu cầu kết quả ổn định trước khi chấp nhận.
   Thời gian xử lý của máy tính có thể làm tăng độ trễ.
6. Xác nhận nhãn web khớp LCD. Nhãn `NONE` hiển thị trạng thái chờ và không đọc thành tiếng.

Mô hình chạy trên máy tính, không chạy trên ESP32. Các file model, scaler và
label encoder được đọc từ `SmartSignLanguage` bất kể terminal đang ở thư mục nào.

## 4. Cảm biến uốn tự động

- Chọn đúng ánh xạ **flex1 → ngón trỏ/ngón giữa**, theo cách gắn cảm biến thực tế.
- Mặc định **Tự động**: kết nối rồi duỗi/gập tay, không cần bấm ghi mốc.
  Web dùng mốc ước lượng từ dữ liệu găng hiện tại: flex1 **931 → 833**, flex2
  **1041 → 933** (số đo giảm khi gập). Mốc tự mở rộng theo cử động; lọc trung vị
  5 mẫu và vùng bỏ qua 8 ADC giúp giảm rung. Khi bắt đầu gần tư thế duỗi và đứng
  yên 20 mẫu, web tự bù sai lệch nhỏ do cách đeo. Kết nối lại sẽ nhận lại mốc tự động.
- Độ gập là ước lượng, không phải phép đo góc chính xác. Nếu thay cảm biến hoặc
  đổi chiều mạch điện, chọn **Tự ghi mốc duỗi / gập**, ghi hai tư thế. Mỗi cảm biến
  cần hai mốc chênh ít nhất 50 ADC; cảm biến đủ mốc hoạt động độc lập.
  Chọn lại **Tự động** bất cứ lúc nào để bỏ qua mốc thủ công.
- Chế độ và mốc thủ công được lưu trong trình duyệt. Demo dùng dải riêng,
  không thay thế mốc của găng thật. Xem **ADC hiện tại / Độ gập** để kiểm tra tín hiệu.
- Ba ngón chưa có cảm biến giữ tư thế mô phỏng, không phải giá trị đo.
- Giữ tay ở tư thế trung tính và dùng nút đặt lại hướng MPU6050.
- Gia tốc có đơn vị m/s²; gyro có đơn vị rad/s. Web ước tính hướng từ cả hai,
  không coi vận tốc góc là góc quay. Yaw chỉ là hướng tương đối và có thể trôi;
  dùng nút đặt lại hướng khi cần.

Các phép hiệu chuẩn trên web chỉ phục vụ dựng hình, không thay đổi 12 đặc trưng
đầu vào mô hình AI. Confidence hiển thị từ Python theo thang 0–1, đổi ra phần trăm
ở giao diện. Kết quả chưa được chấp nhận không được đọc thành tiếng.

## 5. Nếu hai phần chạy trên hai máy

Trên máy chạy AI, cho WebSocket lắng nghe trên mạng nội bộ:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/wifi_ai.py --pipeline legacy --esp32-host 192.168.137.115 --ws-host 0.0.0.0
```

Trên web, thay `localhost` bằng IP của **máy chạy Python**, ví dụ
`ws://192.168.137.1:8765`. Hai máy phải kết nối được với nhau; cấu hình tường lửa
cho cổng 8765 nếu cần. Địa chỉ web HTTP và địa chỉ WebSocket là hai cấu hình riêng.
Hướng dẫn hiện tại dành cho demo trong mạng nội bộ qua HTTP; một trang HTTPS cần WSS.

## 6. Phân công và dữ liệu chung

| Phần | File chính | Công việc |
|---|---|---|
| Web của bạn | `mophong1.html`, `mophong1.css`, `mophong1.js`, `hand-bridge.js`, `hand-connection.js` | Dựng hình, giao thức, hiệu chuẩn, hiển thị, giọng nói |
| AI của bạn cùng nhóm | `SmartSignLanguage/wifi_ai.py` và mô hình | Nhận sensor, suy luận, gửi WebSocket và LCD |
| Firmware dùng chung | `mophong_wireless/mophong_wireless.ino` | Đọc cảm biến, phục vụ một kết nối Python |

Định dạng gói tin và ý nghĩa các trường: [docs/protocol.md](docs/protocol.md).
Mỗi bên phải giữ đúng phiên bản giao thức, đơn vị đo và tên nhãn khi thay đổi code.

Chỉ giữ một bản sketch đầy đủ trong thư mục Arduino đang build. Bản firmware trùng
được lưu ở `firmware_archive/mophong_wireless1.ino` để không bị biên dịch cùng bản chính.

Khi dùng các chương trình thu dữ liệu kết nối trực tiếp ESP32, dừng `wifi_ai.py`
trước: firmware phục vụ một TCP client tại một thời điểm. `train.py` hiện huấn luyện
`dataset_gesture.csv`; dữ liệu câu chưa tự động được đưa vào mô hình này. Chạy
huấn luyện từ thư mục `SmartSignLanguage` để các đường dẫn tương đối của script cũ đúng.

Thu câu/cử chỉ qua firmware dùng chung (Enter bắt đầu, Enter kết thúc):

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage/collect_sentence_wifi.py --esp32-host 192.168.137.115 --label XIN_CHAO
```

Mặc định ghi `dataset_sentence.csv`; dùng `--output` để chọn file khác. Chương trình
đọc sensor liên tục trong lúc chờ Enter, lưu riêng đoạn `BEGIN` → `END`, và đặt
thời điểm mẫu đầu của mỗi trial về 0. Trial bị ngắt kết nối không được lưu.
Trial có dữ liệu lỗi, khoảng cách hai mẫu lớn hơn 250 ms hoặc dưới 5 mẫu cũng
bị loại. Hãy ghi nhiều trial ngắn và giữ tư thế nghỉ giữa các lần thực hiện.

## 7. Kiểm tra trước khi trình diễn

Hướng dẫn từng bước để phân biệt lỗi gập ngón, nhận diện và âm thanh:
[Chạy găng và kiểm tra kết quả](docs/chay-gang-va-nhan-dien.md).
Sau khi cập nhật, khởi động lại Python bridge và Ctrl + F5 trên web. Bảng
**Nhận diện và giọng nói** hiển thị nhãn AI thô, confidence, lý do chưa đọc,
khoảng cách thời gian mẫu AI với mẫu cảm biến mới nhất và trạng thái phát tiếng.
Web đọc tiếng Anh: `XIN_CHAO` → **Hello**, `CAM_ON_NHIEU` → **Thank you very much**.
Mỗi lượt được chấp nhận lưu đoạn chuyển động để phát lại cùng lời đọc. Cả hai
hoàn tất mới tới lượt tiếp theo; mục **Chờ N cử chỉ** hiển thị hàng chờ.
Nếu lỗi giọng đọc, bấm **Thử lại lời đọc** hoặc **Bỏ qua cử chỉ**.
Nút **Thử loa** kiểm tra âm thanh; **Đọc lại kết quả** đọc nhãn được chấp nhận
còn mới, kể cả khi giữ nguyên tay. Phản hồi trình duyệt không xác nhận âm lượng
loa thực tế: người dùng vẫn cần nghe thử.

- Kết nối web: trạng thái Python và ESP32 được hiển thị riêng.
- Duỗi/gập từng ngón: ngón 3D đúng cảm biến và đúng chiều ở chế độ tự động; có thể dùng mốc thủ công nếu thay găng.
- Thực hiện `XIN_CHAO`, về nghỉ, lặp lại: mỗi lần nhận diện được đọc một lần.
- Ngắt ESP32 hoặc Python: nhãn cũ bị xóa; không phát âm lại dữ liệu cũ.
- Khôi phục kết nối: web nhận phiên dữ liệu mới và chờ AI sẵn sàng.
- Chuyển sang demo cục bộ: điều khiển thử không ghi đè kết quả AI thật.

Kiểm tra trong trình duyệt Chrome bằng chế độ demo (không cần găng):

```powershell
.\.bridge-venv\Scripts\python.exe tests/browser_smoke.py
```

Script tự chạy HTTP, bridge demo và Chrome headless, rồi dừng các tiến trình mình
tạo. Ảnh và log nằm trong `.runtime/browser-smoke`. Có thể chỉ định đường dẫn Chrome
bằng `--chrome`. Kiểm tra phần mềm này không thay thế thử cảm biến và nạp firmware thật.

Kiểm tra giao thức, cầu nối, thu dữ liệu và logic web:

```powershell
.\.bridge-venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
node tests/web_bridge.test.js
```

Máy hiện tại không có `node` trong PATH; có thể dùng runtime đi kèm VS Code:

```powershell
$env:ELECTRON_RUN_AS_NODE = '1'
& "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe" tests/web_bridge.test.js
Remove-Item Env:ELECTRON_RUN_AS_NODE
```

Đã kiểm tra: **32 bài Python**, **24 bài logic web**, và luồng Chrome headless
gồm nạp mô hình 3D, nhận WebSocket, gập tự động không ghi mốc, hiệu chuẩn thủ công, giao diện hẹp, mất kết nối và tự
kết nối lại. Firmware đã build thành công với ESP32 core 2.0.14, board
`esp32:esp32:esp32` (Flash 58%, RAM tĩnh 13%). Các file mô hình hiện có đã nạp và
suy luận thử được. Chưa xác minh độ chính xác hoặc thời gian đáp ứng trên găng thật.


## Cấu hình Wi-Fi sau khi tải dự án từ GitHub

Trước khi biên dịch firmware, sao chép `wifi_secrets.example.h` thành
`wifi_secrets.h` trong cùng thư mục với sketch đang dùng (`mophong_com/`,
`mophong_wireless/`, hoặc `firmware_archive/`). Điền tên mạng và mật khẩu
Wi-Fi của bạn trong tệp mới. `wifi_secrets.h` được Git bỏ qua; không tải tệp
này lên GitHub. Trên máy hiện tại, cấu hình Wi-Fi đã được giữ trong tệp cục bộ.

Kho chứa mã nguồn, dữ liệu thu, mô hình đã huấn luyện, tài liệu và báo cáo.
Môi trường chạy, cache, tệp làm việc tạm và cấu hình riêng của máy được bỏ qua.
