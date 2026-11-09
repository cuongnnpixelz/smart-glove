# Thu cử chỉ mới đơn giản bằng hai flex + MPU6050

> **Quy trình hiện tại:** [Demo chuỗi 5 giây, hai flex và dFlex](demo-chuoi-5s.md).
> Các launcher `chay-thu-cu-chi.ps1`, `chay-train-chuoi.ps1`,
> `chay-nhan-dien-chuoi.ps1` đã chuyển sang quy trình đó. Phần bên dưới ghi lại
> luồng 3 giây cũ để đối chiếu, không dùng để thu bộ dữ liệu mới.

Mỗi trial chứa **toàn bộ chuỗi động tác** gán chung một nhãn, ví dụ
`NGHIENG_GAP_DUOI`. Dùng ESP32 và Python, không cần web. Bộ thu lưu hai flex,
IMU gốc, quaternion và gia tốc sau trừ trọng lực. Không yêu cầu hiệu chuẩn flex.

## Cách chạy

Nạp firmware mới trong `mophong_wireless/mophong_wireless.ino`, đóng Serial Monitor,
dừng `wifi_ai.py`, sau đó chạy tại thư mục dự án:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\collect_sequence.py --user-id U01 --esp32-host 192.168.137.115 --label NGHIENG_GAP_DUOI --seconds 3
```

Thay IP nếu găng có địa chỉ khác. Nếu đang chạy bản cũ, nhấn `Q` để thoát trước.

1. Sau khi kiểm tra RAW2, đặt tay yên trên bàn, nhấn Enter để lấy mốc MPU.
2. Sau đếm 3–2–1, giữ yên khoảng 4 giây để đo độ lệch gyro và khởi tạo hướng.
   Chỉ làm một lần đầu phiên, không phải gập/duỗi để hiệu chuẩn flex.
3. Chờ `SAN SANG`, đưa tay về tư thế đầu, nhấn Enter ở menu thu.
4. Chờ `BAT DAU`, làm nghiêng → gập hai ngón → duỗi → cổ tay về giữa,
   trọn chuỗi đúng một lần trong 3 giây. Chờ `DA LUU trial ...`.

Trong menu:

- Enter: đếm 3–2–1 và thu trọn chuỗi trong 3 giây.
- `C`: nhập nhãn khác, ví dụ `NONE`.
- `Q`: kết thúc phiên.

Chỉ dùng chữ A–Z, số và dấu gạch dưới cho nhãn. Mỗi nhãn phải đại diện cho một
động tác rõ ràng, không dùng cùng tên cho hai cách làm khác nhau.

Dữ liệu được tạo riêng:

```text
SmartSignLanguage/sequence_data/<ma-phien>/samples.csv
```

Header mới:

```csv
timestamp,user_id,session_id,trial_id,label,flex_1,flex_2,Qw,Qx,Qy,Qz,GYRx,GYRy,GYRz,ACCx,ACCy,ACCz,ACCx_body,ACCy_body,ACCz_body,ACCx_world,ACCy_world,ACCz_world
```

| Nhóm | Nội dung |
|---|---|
| timestamp | Mili giây từ mốc thời gian thiết bị |
| user_id, session_id, trial_id, label | Người thu, phiên, lần thu, nhãn cả chuỗi |
| flex_1, flex_2 | ADC gốc, chưa chuẩn hóa về [0,1] |
| Qw, Qx, Qy, Qz | Quaternion ước lượng, từ hệ cảm biến sang hệ tham chiếu cục bộ |
| GYRx, GYRy, GYRz | Gyro gốc, rad/s |
| ACCx, ACCy, ACCz | Gia tốc gốc gồm thành phần trọng lực, m/s² |
| ACCx_body, ACCy_body, ACCz_body | Gia tốc đã trừ trọng lực ước lượng, trong hệ cảm biến |
| ACCx_world, ACCy_world, ACCz_world | Gia tốc trên xoay sang hệ tham chiếu cục bộ |

Không tạo ba flex còn thiếu. Không cần lưu dFlex; có thể tính từ flex và timestamp.
File `imu_reference.json` cùng thư mục lưu phiên bản xử lý, mốc gyro/trọng lực,
đơn vị và thời lượng. Bộ lọc chạy liên tục cả lúc chờ menu, không reset mỗi trial.

Quaternion/body/world là giá trị tính toán, không phải kênh đo độc lập. Dự án dùng
bộ lọc bù trọng lực trong Python, không tuyên bố giống thuật toán dataset tham khảo.
Hướng world tương đối theo lúc khởi tạo, không phải hướng Bắc tuyệt đối.
Sai số hướng và chuyển động có thể làm sai phần trừ trọng lực.

CSV phiên cũ giữ header cũ. Không ghép hai định dạng vào cùng file hoặc điền số 0
giả cho các cột thiếu. Chạy lại bộ thu để tạo phiên mới; mở đường dẫn `File moi:`.

Nếu hiện `TAM DUNG: Du lieu ESP32 bi gian doan ... ms`, khoảng cách timestamp giữa
hai mẫu đã vượt 120 ms. Bộ lọc không thể tiếp tục tính hướng chính xác qua đoạn
thiếu đó. Lần thu chưa hoàn tất không được ghi; các trial đã lưu vẫn còn.
Nhấn Enter ở lời nhắc phục hồi để kết nối lại và tạo phiên mới, rồi giữ yên tay
lấy lại mốc MPU. Nhấn Q nếu muốn dừng. Phiên mới có file và hệ tham chiếu mới,
không ghép đoạn trước/sau gián đoạn vào cùng một trial. Mất kết nối, timestamp
quay ngược hoặc gói sai định dạng vẫn yêu cầu kiểm tra ESP32 và chạy lại.

## Cách thu để tạo chuỗi

Thu khoảng 20–30 trial cho mỗi nhãn làm demo ban đầu, qua nhiều lần đeo găng.
Mỗi trial thực hiện toàn bộ chuỗi đúng một lần. Thu `NONE` cho nghỉ và chuyển động
không thực hiện đủ chuỗi. Số trial này không bảo đảm độ chính xác.

Thêm cột không tự làm model tốt hơn. Khi train cần chọn đặc trưng, chuẩn hóa và
tách tập kiểm tra theo phiên; khi nhận diện phải dùng cùng cách xử lý dữ liệu.
`train.py`/`train_v2.py` hiện yêu cầu hiệu chuẩn flex và nhãn khác. Với bộ chuỗi
mới, dùng `train_sequence.py` bên dưới.

## Train và thử nhận diện bằng Python

Sau khi kết thúc thu bằng Q, chạy:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\train_sequence.py
```

Bộ train kiểm tra timestamp, thời lượng 3 giây, quaternion và gia tốc tính toán.
Phiên chỉ có file mốc hoặc CSV rỗng được bỏ qua; trial thiếu/hỏng không được tự
ghép hoặc kéo giãn. Cần ít nhất hai nhãn, có `NONE`.

Model SVM học trọn chuỗi trên lưới 76 mẫu cách nhau 40 ms. Đặc trưng gồm thay đổi
hai flex so với đầu chuỗi (không phải hiệu chuẩn [0,1]), quaternion tương đối với
đầu chuỗi, gyro đã trừ độ lệch và gia tốc body. CSV vẫn giữ đầy đủ các cột; model
không đưa mọi cột dư thừa vào đầu vào. StandardScaler chỉ học từ tập train.

Nếu có thể giữ riêng phiên mà cả tập train/test đều đủ nhãn, chương trình sẽ
chia theo phiên. Nếu không, chỉ chia theo nguyên trial và báo rõ đánh giá demo
trong phiên. Không chia từng dòng hoặc cửa sổ chồng lấn sang hai tập. Các siêu
tham số SVM cố định; không điều chỉnh dựa trên kết quả tập test.

Mỗi lần train tạo thư mục mới `SmartSignLanguage/models/sequence_<ma>/` gồm:
`model.joblib`, `manifest.json` và `report.json` (danh sách trial train/test,
confusion matrix, nguồn dữ liệu và giới hạn đánh giá). Không ghi đè model cũ.

Lần train ngày 07/10/2026 dùng 30 trial `NGHIENG_GAP_DUOI`, 27 trial `NONE`:
42 trial train, 15 trial test. Kết quả 15/15 đúng chỉ là kiểm tra trong hai phiên
cũ (mỗi phiên một nhãn), chưa kiểm chứng độ chính xác ở phiên mới.

## Điều kiện hai flex trước khi nhận diện

Ánh xạ đã đo trên găng hiện tại: ngón trỏ = `flex_2`, ngón giữa = `flex_1`.
Giữ nguyên cả hai kênh. Chạy `check_flex.py` sau khi chỉnh cách gắn/dây và trước
khi thử nhận diện. Báo cáo mới tách riêng ba điều: xác định kênh, hồi về sau duỗi,
và ổn định khi ngón khác cử động. Xác định đúng kênh không có nghĩa cảm biến đã ổn.

Nếu ngón trỏ duỗi mà flex_2 giảm rõ khi ngón giữa cử động, kiểm tra ngón trỏ có
co theo hay phần găng/dây có kéo cảm biến cong; đặt cảm biến theo chiều gập của
ngón, tránh gấp nếp và để dây đủ chùng. Nếu vẫn bất thường, kiểm tra riêng cảm
biến/mạch. Phần mềm không khẳng định linh kiện hỏng chỉ qua bài đo này.

Chương trình nhận diện dùng báo cáo `diagnostics/*/flex_check.json` mới nhất,
hoặc chỉ định bằng `--flex-report`. Cả hai kênh phải qua kiểm tra. Nó cũng so
mức duỗi hiện tại với mốc trong báo cáo để từ chối mốc đã lệch sau khi đeo lại.

Model báo `NGHIENG_GAP_DUOI` còn phải qua kiểm tra bắt buộc: bắt đầu duỗi hai ngón,
gập cả hai trước khi nghiêng, giữ gập, nghiêng đúng hướng, cổ tay trở về, rồi
duỗi cả hai. Thiếu bước sẽ in `NONE` kèm lý do. Hướng được lấy từ 22 trial train
của model demo, không dùng 8 trial dương trong tập test. Ngưỡng gập/duỗi lấy theo
biên đo từng flex; các tỷ lệ và dung sai trong bộ chặn là quy tắc demo, cần kiểm
chứng trên găng, không phải cam kết nhận diện chính xác.

`acceptance_guard.json` gắn với hash của model. `train_sequence.py` tạo file này
cho bộ hai nhãn `NONE` và `NGHIENG_GAP_DUOI`. Với các chuỗi khác cần thiết kế bộ
kiểm tra tương ứng, không dùng nguyên luật gập hai ngón này cho mọi nhãn.

Để thử model demo đã lưu, đóng bộ thu bằng Q rồi chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\chay-nhan-dien-chuoi.ps1
```

Giữ yên lấy mốc MPU. Mỗi lần nhấn Enter, sau đếm 3–2–1 thực hiện một chuỗi 3 giây
hoặc nghỉ/chuyển động khác để kiểm tra `NONE`. Kết quả in ra terminal. Chương trình
này không lưu dữ liệu và không tự phân đoạn luồng liên tục. Khi có gap, không
đoán từ đoạn thiếu; cần chạy lại để lấy mốc MPU.

Script trên trỏ tới model demo `sequence_20261007T100410Z_9293f450`.
Sau khi train model khác, dùng `predict_sequence.py --model <thu-muc-model-moi>`.
Nên kiểm tra cả hai nhãn trong cùng một lần đeo găng mới; thu phiên độc lập có cả
hai nhãn trước khi khẳng định chất lượng nhận diện.
