# Găng tay chạy trực tiếp trên ESP32-S3 N16R8

Thư mục này là bản firmware riêng. ESP32-S3 tự đọc 5 flex + MPU6050,
chạy model ExtraTrees 300 cây và xuất kết quả qua Serial. Python chỉ dùng
khi xuất/kiểm tra model trên máy, không tham gia nhận diện sau khi nạp.

## Những gì đã có

- Model **14 từ + NONE**, không có ĐIỆN THOẠI:
  `AN BAN BUON_BA CAM_ON CHAO DANG_LAM DI_DAU GI KHOE O_DAU TEN THICH TOI TUYET_VOI`.
- Giữ nguyên model đã train toàn bộ 642 lượt; không train lại, không cắt cây.
- 300 cây, 47.966 nút; các bảng cây chiếm **576.192 byte trong flash**.
  Tất cả lá thuần một nhãn nên có thể lưu bằng mã nhãn. Ngưỡng cây được xuất
  theo quy tắc giữ nguyên nhánh so sánh với đầu vào float32 của sklearn.
- Đọc 100 Hz trong task riêng; cửa sổ 150 mẫu thật / 1,5 giây; dự đoán mỗi
  250 ms. Vòng đọc cảm biến tiếp tục chạy trong khi task còn lại dự đoán.
- Hiệu chuẩn 5 flex, lưu mốc vào NVS. Mỗi lần bật nguồn lấy lại bias và hướng MPU.
- MPU ±4g, ±1000 độ/giây, DLPF 21 Hz, sample-rate divisor 9, như firmware cũ.
- Chuẩn hóa flex, median 5 mẫu, bộ lọc quaternion, đặc trưng gravity/body/gyro
  và dFlex tương ứng với Python.
- Test từng từ, ghép câu, cảnh báo flex theo kênh và báo mất mẫu/bão hòa MPU.

Kết quả hiện ra bằng nhãn ASCII trong Serial Monitor, ví dụ `TOI`, `CAM_ON`.
**Bản này chưa phát loa, gọi API giọng nói, dịch ngôn ngữ hay điều khiển LCD.**
Các chức năng đó cần tích hợp sau khi xác nhận nhận diện trên S3 hoạt động.

## 1. Xác nhận đúng bo và nối dây

Cấu hình đích: **ESP32-S3-WROOM-1 N16R8**, flash 16 MB, Octal/OPI PSRAM 8 MB,
kiểu chân DevKitC. Đọc số GPIO in trên bo; không đếm thứ tự chân vật lý.
Nếu bo khác loại, đối chiếu pinout trước khi nối.

Tắt nguồn rồi chuyển dây theo bảng:

| Tín hiệu | ESP32 cũ | ESP32-S3 trong bản này |
|---|---:|---:|
| Flex cái F1 | GPIO32 | **GPIO4** |
| Flex trỏ F2 | GPIO33 | **GPIO5** |
| Flex giữa F3 | GPIO34 | **GPIO6** |
| Flex áp út F4 | GPIO35 | **GPIO7** |
| Flex út F5 | GPIO36 | **GPIO8** |
| MPU SDA | GPIO27 | **GPIO11** |
| MPU SCL | GPIO26 | **GPIO12** |
| MPU VCC | 3,3V | **3,3V** |
| MPU GND, GND điện trở | GND | **GND chung** |

Mỗi flex vẫn dùng mạch:

```text
3,3V ── FLEX ──┬── GPIO của ngón đó
              └── điện trở 10 kΩ ── GND
```

Giữ thứ tự cái–trỏ–giữa–áp út–út. Sai thứ tự sẽ làm model nhận nhầm.
ADC của S3 khác ESP32 cũ nên cần đo lại mốc flex trên S3, không chép mốc ADC cũ.

Để trống GPIO19/20 cho USB native. Không dùng GPIO35/36/37 vì bản Octal PSRAM
dùng các chân này bên trong. GPIO32–36 cũ không phải bộ chân flex của bản S3.

Các chân **chỉ dành sẵn cho bước mở rộng, chưa điều khiển**:

| Phần mở rộng | Chân dành sẵn |
|---|---|
| LCD I²C | SDA15, SCL16 |
| MAX98357A | BCLK17, LRC18, DIN21 |

Không tiếp tục dùng bộ chân loa 18/19/23 của bo cũ trên bản S3 này.
Hiện chưa cần nối LCD hoặc loa để kiểm tra model.

## 2. Nạp bằng PowerShell

Tại thư mục dự án `C:\Users\Admin\Downloads\newbie4`, đóng Python và Serial
Monitor đang dùng COM. Cắm **bo S3**, xem đúng COM trong Device Manager.
COM có thể khác COM3 của bo cũ.

Với cổng USB–UART (thường ghi UART/COM, dùng CH340/CP210x):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\esp32_s3_standalone\nap-s3.ps1 -Port COM3
```

Thay `COM3` bằng COM thực tế của S3.

Nếu dùng cổng **USB native** của S3, thêm `-NativeUsb`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\esp32_s3_standalone\nap-s3.ps1 -Port COM3 -NativeUsb
```

Chỉ biên dịch, chưa nạp:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\esp32_s3_standalone\nap-s3.ps1 -CompileOnly
```

Script dùng Arduino CLI có sẵn trong Arduino IDE, không thay execution policy
vĩnh viễn. Tốc độ nạp được đặt rõ là **115200 baud** để hạn chế lỗi đường truyền;
đây là thiết lập riêng với baud của Serial Monitor. Nếu kết nối nạp không được, giữ BOOT, bấm RESET, thả BOOT rồi thử
lại; USB native có thể xuất hiện COM mới sau nạp/reset.

## 3. Nạp bằng Arduino IDE

Mở **`firmware/firmware.ino`**, để nguyên các file `.h`/`.cpp` bên cạnh.

1. Cài board package **esp32 by Espressif Systems**. Phiên bản dùng để biên dịch
   bản này: **2.0.14**.
2. Chọn board **ESP32S3 Dev Module**.
3. Chọn **Flash Size: 16MB**, **PSRAM: OPI PSRAM**.
4. Chọn **Partition Scheme: 16M Flash (3MB APP/9.9MB FATFS)**.
5. Cổng USB–UART: **USB CDC On Boot: Disabled**.
   Cổng USB native: **USB Mode: Hardware CDC and JTAG**, **USB CDC On Boot: Enabled**.
6. Cài thư viện **Adafruit MPU6050**, **Adafruit Unified Sensor**,
   **Adafruit BusIO** qua Library Manager.
7. Chọn đúng Port rồi Upload.

Đã có `model_data.cpp` được xuất sẵn; không cần chạy Python để nạp bản này.

## 4. Lần chạy đầu và hiệu chuẩn

Mở Serial Monitor **115200 baud**, chọn **Newline**. Nếu không thấy banner,
bấm RESET khi monitor đã mở.

Lần đầu chưa có mốc flex:

1. Khi hỏi DUỖI, duỗi 5 ngón thoải mái, nhấn Enter. Chờ đếm ngược, giữ yên
   3 giây; máy dùng 2 giây cuối.
2. Khi hỏi GẬP, gập cả 5 ngón vừa phải (cả khớp ngón cái), nhấn Enter và giữ yên.
3. Máy báo từng F1–F5 đạt/chưa đạt. Nếu chưa đạt, chỉnh đúng ngón/dây rồi đo lại.
4. Đặt tay yên để tự lấy mốc MPU. Nếu phát hiện đang chuyển động, máy cảnh báo
   và tự đo lại, giữ nguyên kết quả flex.
5. Tiếp tục giữ yên trong lúc bộ lọc MPU khởi tạo. Sau đó chờ đủ cửa sổ 1,5 giây.

Các lần bật nguồn sau dùng mốc flex đã lưu và tự lấy mốc MPU. Không cần máy tính
để suy luận, nhưng kết quả ở bản này chỉ quan sát được qua Serial. Cần đặt tay
yên trong quá trình khởi động. Nếu tháo/đeo lại găng hoặc chỉnh cảm biến, mở
Serial và gửi **C** để đo lại flex.

## 5. Test từng từ và ghép câu

| Gửi trong Serial Monitor | Chức năng |
|---|---|
| **W** | Test từng từ liên tục, chế độ mặc định |
| **S** | Ghép câu, chốt sau 10 cửa sổ NONE liên tiếp |
| **Enter** khi đang ghép câu | Chốt câu thủ công |
| **F** | Bật/tắt số flex chuẩn hóa mỗi giây |
| **C** | Xóa mốc flex đã lưu và khởi động lại để hiệu chuẩn |

Chế độ W hiển thị nhãn sau hai dự đoán liên tiếp giống nhau, rồi tiếp tục cập
nhật. `model ... ms` là thời gian duyệt cây, không gồm thời gian thu 1,5 giây.

Chế độ S giữ các nhóm nhãn, lọc khi chốt câu. Ngưỡng được chép từ code Python
hiện tại: từ thường ≥5; CẢM ƠN và TÊN ≥3; ĐI ĐÂU, Ở ĐÂU, TUYỆT VỜI ≥4 cửa sổ.
Các ngoại lệ sửa theo ngữ cảnh đang có trong Python cũng được chuyển sang
`sentence.h`. Đây là quy tắc hiển thị của dự án, không phải khả năng dịch VSL tổng quát.

Nếu model không phát NONE ở tư thế nghỉ, dùng Enter chốt để xem nguyên chuỗi.
Không có giới hạn 5 giây. Nếu vượt 128 nhóm nhãn, máy hủy câu và báo để bạn
chia câu ngắn hơn; không trả câu bị cắt cụt.

Lỗi ADC sát biên, MPU bão hòa/đọc lỗi hoặc mất mẫu sẽ hủy cửa sổ và câu đang xét.
Giống chính sách runtime hiện tại trong Python: bước nhảy flex còn nằm trong
miền ADC chỉ cảnh báo; median 5 mẫu vẫn do model xử lý. Lỗi dây vẫn có thể làm
đoán sai, cần sửa phần cứng trước khi đánh giá.

## 6. Kiểm tra bản chuyển đổi

`verification.json` ghi kết quả so sánh **C++ chạy trên máy tính** với Python:
duyệt cây, đặc trưng, bộ lọc MPU và quy tắc ghép nhãn. Đây không phải đo độ
chính xác trên găng thật, cũng không phải đo tốc độ chip S3.

Kết quả kiểm tra ngày 18/11/2026:

- Nhãn C++ khớp Python **642/642 lượt**.
- Tạo đặc trưng C++ trên 642 cửa sổ không làm đổi nhãn; sai số tuyệt đối lớn
  nhất so với Python khoảng `1,39e-17` trên dữ liệu kiểm tra.
- Bộ lọc MPU chạy lại từ mốc đứng yên khớp Python trong sai số khoảng `1,07e-14`.
- **2.001 chuỗi** thử bộ lọc nhãn cho kết quả khớp Python.
- Biên dịch core 2.0.14, cổng UART: chương trình **907.873 byte**, biến toàn cục
  **116.612 byte**, phần RAM còn lại theo linker **211.068 byte** trước cấp phát
  động và stack task. Không coi số cuối là heap trống đo trên chip.

Các bảng model được đọc từ flash; bản hiện tại chưa cần dùng PSRAM cho model.
Đã biên dịch, **chưa nạp lên bo** và chưa đo tốc độ/độ chính xác cảm biến trên S3.

Model nguồn train toàn bộ dữ liệu, không có tập test độc lập. Việc chuyển đổi
không sửa các lỗi TÔI/TÊN, KHỎE/GÌ đã tồn tại trong model hoặc cảm biến.

Muốn xuất lại đúng model nguồn:

```powershell
python .\esp32_s3_standalone\export_model.py
```

`model_info.json` lưu SHA256 và cấu trúc model để truy nguyên. Exporter cố ý chỉ
nhận đúng cấu trúc 14 từ hiện tại; thêm từ/train model khác cần cập nhật exporter
và kiểm tra lại, không thay file dữ liệu cây thủ công.

## Tài liệu chân bo

- [Espressif ESP32-S3 DevKitC-1](https://documentation.espressif.com/api/resource/path/docs/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide.html)
- [USB CDC của Arduino-ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/cdc_dfu_flash.html)

Không nạp sketch này lên ESP32 DevKit V1 thường. Các file trong thư mục firmware
cũ và các dataset/model Python vẫn dùng ở vị trí hiện tại.
