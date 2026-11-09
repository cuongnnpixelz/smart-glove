# Demo hai flex + MPU: thu trọn chuỗi 5 giây

> **Chế độ sử dụng hiện tại:** [Nhận diện liên tục, không cần Enter](nhan-dien-lien-tuc.md).
> `chay-nhan-dien-chuoi.ps1` đã chạy `predict_continuous.py`. Các lệnh
> `predict_sequence_v2.py` bên dưới là công cụ kiểm tra từng lượt thủ công.

## Hiện kết quả trên LCD ESP32

Nạp lại `mophong_wireless/mophong_wireless.ino` để hỗ trợ lệnh `SEQ` mới,
rồi chạy `predict_sequence_v2.py` như bình thường. Không cần train lại model.

| Nhãn nhận diện cuối cùng | LCD 16x2 (không dấu) |
|---|---|
| `TRO_TRAI_DUOI` | `XIN CHAO` |
| `GIUA_TRAI_DUOI` | `CAM ON` |
| `TRO_PHAI_DUOI` | `TAM BIET` |
| `NONE` hoặc nhãn chưa ánh xạ | `CHUA NHAN DIEN` |

Nhấn Enter, thực hiện một chuỗi 5 giây. Sau khi xử lý, Python gửi kết quả qua
cùng kết nối TCP về LCD. Dòng hai ghi `KET QUA CUOI`; kết quả được giữ đến khi
bắt đầu lượt mới, có kết quả mới, hoặc mất kết nối. Chương trình vẫn nhận diện
theo từng lượt Enter, chưa tự chia cử chỉ liên tục. Màn hình không in phần trăm
tin cậy giả cho SVM. Giữ chữ không dấu vì cách in hiện tại không hỗ trợ UTF-8.

Giao thức thêm: `SEQ,XIN_CHAO\n`, `SEQ,CAM_ON\n`, `SEQ,TAM_BIET\n`,
`SEQ,NONE\n`. Giao thức `AI,label,confidence` của web vẫn hoạt động như cũ.

## Nhãn tự nhập, chỉ gập một ngón: train sơ bộ

Với `TRO_TRAI_DUOI`, `GIUA_TRAI_DUOI`, `TRO_PHAI_DUOI` thu thủ công,
dùng chế độ SVM học trực tiếp từ các nhãn, không áp bộ luật gập cả hai ngón:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\train_sequence_v2.py --allow-trial-split --motion-checks classifier-only
```

`--allow-trial-split` cho phép thử sơ bộ khi các cử chỉ chưa có ở nhiều phiên.
Nếu đủ phiên, chương trình vẫn ưu tiên chia theo phiên. `classifier-only` được ghi
vào model và báo cáo; chương trình nhận diện sẽ hiện cảnh báo chưa có kiểm tra
riêng ngón/thứ tự. Đây không phải chế độ đã đảm bảo chống nhận nhầm khi chỉ nghiêng.
Cả hai flex, hai dFlex và các kênh IMU vẫn là đầu vào AI như trước.
Không dùng luật gập cả hai ngón để kết luận dữ liệu một ngón là sai.

Train xong chạy `predict_sequence_v2.py` như bước 5. Cần kiểm tra riêng chuỗi đúng,
chỉ nghiêng, chỉ gập và sai ngón. Điểm test trong phiên chưa chứng minh độ chính
xác sau khi đeo lại găng. Các hướng dẫn về bộ luật cả hai ngón bên dưới dành cho
demo ban đầu, không áp dụng cho model `classifier-only`.

Đây là quy trình hiện tại cho **gập cả hai ngón → nghiêng một hướng cố định →
đưa cổ tay về giữa → mới duỗi hai ngón**. Cả chuỗi mang một nhãn `NGHIENG_GAP_DUOI`.
Tên nhãn được giữ để dễ đối chiếu; thứ tự thực hiện là **gập trước, nghiêng sau**.
Chỉ dùng Python và ESP32. Theo lần kiểm tra của bạn: `flex_1` là ngón giữa,
`flex_2` là ngón trỏ; giữ nguyên dây và cách gắn trong khi thu.

**Trạng thái sau khi dọn ngày 08/10/2026:** đã xóa dữ liệu/model cũ và báo cáo
flex theo yêu cầu để bắt đầu lại. Thư mục dữ liệu 5 giây và model trống;
bạn bắt đầu từ bước 1. Mã nguồn và môi trường Python vẫn còn đầy đủ.

## 1. Chuẩn bị

- Giữ firmware RAW2 đã nạp, 25 Hz; **không cần nạp lại ESP32** cho thay đổi này.
- Dừng chương trình Python khác đang nối găng. Chỉ một chương trình kết nối TCP.
- Mở PowerShell tại `C:\Users\Admin\Downloads\newbie4`.
- Đeo găng, chọn một hướng nghiêng vừa phải và nhớ hướng đó cho tất cả mẫu đúng.

Chạy:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\collect_sequence_v2.py --user-id U01 --esp32-host 192.168.137.115
```

Hoặc chạy `powershell -ExecutionPolicy Bypass -File .\chay-thu-cu-chi.ps1`.
Thay IP nếu ESP32 đổi địa chỉ. Mỗi lần mở tạo một thư mục mới trong
`SmartSignLanguage/sequence_data_v2/`; không ghi đè dữ liệu hoặc model cũ.

Đặt tay yên, nhấn Enter theo lời nhắc, đếm 3–2–1 rồi giữ yên khoảng 4 giây để lấy
mốc MPU. Đây là mốc gyro/trọng lực; không yêu cầu đo ADC duỗi/gập của flex.

## 2. Thực hiện một mẫu đúng

Đọc dòng `MAU ...` và hướng dẫn trước khi nhấn Enter. Sau đếm 3–2–1, chỉ bắt đầu
khi thấy `BAT DAU`. Mốc thời gian dưới đây là hướng dẫn, không cần bấm giờ tuyệt đối:

| Thời gian trong cửa sổ | Động tác |
|---|---|
| 0–0,5 giây | Duỗi hai ngón, cổ tay ở giữa, giữ yên để lấy nền flex của lần này |
| 0,5–1,3 giây | Gập cả ngón trỏ và ngón giữa, giữ cổ tay ở giữa |
| 1,3–2,3 giây | Giữ hai ngón gập, nghiêng cổ tay theo hướng đã chọn |
| 2,3–3,3 giây | Vẫn giữ ngón gập, đưa cổ tay về giữa |
| 3,3–5 giây | Duỗi hai ngón rồi giữ yên đến hết, ghi cả phần cảm biến hồi chậm |

Chỉ làm **một chuỗi mỗi lần thu**. Đầu mỗi lần phải duỗi tay thật, nhưng ADC không
cần bằng đúng lần trước. Không cố kéo/căng cảm biến để ép số về mốc cũ.
Nếu tay/cảm biến chưa ổn định giữa hai lần, nghỉ thêm rồi mới nhấn Enter.

Sau khi thu xong:

- Enter: bạn xác nhận làm đúng lời nhắc và lưu lần này.
- `R`: bỏ lần vừa làm nhầm và thu lại cùng hướng dẫn; các lần đã lưu giữ nguyên.
- `Q`: bỏ lần chưa xác nhận và kết thúc.

`DA LUU` xác nhận dữ liệu qua kiểm tra thời gian và đã ghi CSV, **không tự chứng
minh động tác đúng**. Mỗi lần 5 giây ở 25 Hz thường có khoảng 126 mẫu. Không ép đủ
mẫu bằng cách kéo giãn dữ liệu 3 giây hoặc nối hai lần thu.

## 3. Mẫu NONE phải làm theo lời nhắc

Chương trình tự xen kẽ một mẫu đúng và một mẫu NONE ngay trong cùng phiên.
NONE không chỉ là ngồi yên:

| Lời nhắc | Bạn thực hiện |
|---|---|
| `CHI_NGHIENG` | Hai ngón duỗi, chỉ nghiêng đúng hướng rồi về giữa |
| `CHI_GAP` | Gập rồi duỗi cả hai ngón, cổ tay giữ yên |
| `SAI_HUONG` | Gập hai ngón, nghiêng hướng ngược hướng đúng, về giữa rồi duỗi |
| `THA_SOM` | Gập, nghiêng, duỗi khi tay còn nghiêng, sau đó mới về giữa |
| `MOT_NGON` | Chỉ gập một ngón rồi nghiêng/về/duỗi; đổi trỏ và giữa ở hai lượt |
| `NGHI` | Duỗi và giữ yên suốt cửa sổ |

Mỗi mẫu NONE cũng giữ yên 0,5 giây đầu. Chương trình tự đặt nhãn; không cần bấm C.
Các mẫu này giúp model học sự khác biệt giữa chuỗi đủ và động tác gần giống.

Mặc định **24 mẫu/phiên: 12 đúng + 12 NONE**. Làm **3 phiên**, tổng cộng 36 mẫu
đúng và 36 NONE, là điểm bắt đầu cho demo, không phải số lượng đảm bảo chính xác.
Kết thúc một phiên, nghỉ/tháo đeo lại găng đúng vị trí rồi chạy lại cùng lệnh.
Mỗi phiên đều thu đủ cả hai nhãn. Có thể chia ra các thời điểm khác nhau.
Giữ thứ tự/hướng nhất quán, thay đổi tốc độ nhẹ; đừng cố tạo tín hiệu giống hệt nhau.

Nếu mất dữ liệu trên 120 ms, lần dở không được lưu. Enter để tạo phiên mới và
lấy lại mốc MPU; các mẫu đã lưu vẫn còn, lịch tiếp tục từ mẫu chưa hoàn tất.
Nếu thoát rồi mở lại chương trình, lịch bắt đầu một phiên mới từ đầu.

## 4. Huấn luyện

Thoát thu bằng Q hoặc chờ hoàn tất lịch, rồi chạy:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\train_sequence_v2.py
```

Hoặc `powershell -ExecutionPolicy Bypass -File .\chay-train-chuoi.ps1`.

Bộ train:

- Chỉ đọc thư mục `sequence_data_v2`, yêu cầu cửa sổ đủ 5 giây và đúng cấu trúc.
- Tách cả phiên để kiểm tra, không chia các dòng cùng trial sang cả train/test.
- Fit scaler và học các mức biến thiên/hướng từ **train**, không dùng test.
- Kiểm tra mẫu dương có gập và hồi ở **cả hai flex**. Nếu nhiều mẫu không rõ,
  báo nhãn/trial cần xem thay vì vẫn train rồi báo tốt.
- Báo kết quả cuối gồm SVM và kiểm tra chuỗi; lưu model riêng `models/sequence_v2_*`.

Nếu chỉ có một phiên hoặc mỗi nhãn nằm riêng một phiên, chương trình yêu cầu
thu thêm phiên có đủ nhãn. `--allow-trial-split` chỉ dành cho thử sơ bộ; kết quả
đó không chứng minh hoạt động được sau khi đeo lại găng.

## 5. Thử model trên găng thật

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\predict_sequence_v2.py --esp32-host 192.168.137.115
```

Hoặc `powershell -ExecutionPolicy Bypass -File .\chay-nhan-dien-chuoi.ps1`.
Mặc định chọn model v2 mới nhất, in rõ đường dẫn. Có thể chọn cụ thể bằng
`--model SmartSignLanguage\models\sequence_v2_<ma-model>`.
Nếu chưa train model v2 thì chương trình nhắc thu/train, không dùng nhầm model 3 giây.

Lấy mốc MPU như lúc thu. Enter để kiểm tra một cửa sổ 5 giây; đầu cửa sổ giữ yên
0,5 giây. Không lưu các lần kiểm tra vào dữ liệu train.
Thử riêng 10 lần đúng, 10 lần chỉ nghiêng, 10 lần chỉ gập, 10 lần sai hướng và
một số lần chỉ gập một ngón/thả sớm. Ghi số lần đúng bị bỏ sót và NONE bị nhận nhầm.
Đánh giá này cần bạn thực hiện thật; test phần mềm không thay thế được.

Nếu điều chỉnh code/dữ liệu sau khi xem kết quả, nên dùng thêm một phiên mới để
đánh giá cuối, tránh chọn cách sửa chỉ vì nó hợp với tập test đã xem nhiều lần.

## Dữ liệu và xử lý đã thay đổi gì?

CSV vẫn giữ ADC gốc và đủ các kênh đã thống nhất:

```csv
timestamp,user_id,session_id,trial_id,label,flex_1,flex_2,Qw,Qx,Qy,Qz,GYRx,GYRy,GYRz,ACCx,ACCy,ACCz,ACCx_body,ACCy_body,ACCz_body,ACCx_world,ACCy_world,ACCz_world
```

Python dùng chung một hàm cho train/nhận diện: nội suy theo timestamp lên lưới
40 ms, lọc median flex 3 mẫu, trừ nền 0,5 giây đầu, rồi tính dFlex trên khoảng
160 ms theo đơn vị **ADC/giây**. Không cần thêm dFlex vào firmware/CSV, vì tính
lại được từ tín hiệu gốc. Không gọi giá trị này là tốc độ góc vật lý của ngón tay.

Model dùng 14 kênh theo thời gian: hai flex tương đối, quaternion tương đối,
ba gyro trừ bias, ba gia tốc body và hai dFlex. ADC cuối được phép còn lệch;
kiểm tra mới tìm sự gập rồi hồi sau khi cổ tay về, không bắt trở lại đúng ADC đầu.
Không cần vượt qua báo cáo flex tĩnh cũ mới được chạy quy trình này.

Kiểm tra chuỗi vẫn dùng các ngưỡng demo về biên độ, hướng và thứ tự. Nó có thể
bỏ sót động tác thật và cần kiểm tra trực tiếp; không phải chứng nhận độ chính xác.
Nếu hai động tác tạo tín hiệu không phân biệt được, thêm dFlex không tạo ra thông
tin mới để tách chúng. Dữ liệu không rõ sẽ được báo để sửa cách thu/cảm biến.

Các module Python dùng chung vẫn được giữ; dữ liệu `sequence_data/` cũ đã xóa
theo yêu cầu bắt đầu lại. Không trộn dữ liệu 3 giây vào 5 giây.
`*_sequence_v2.py` là luồng chuỗi này, khác với
`collect_v2.py/train_v2.py/wifi_ai.py` của luồng web cũ.
