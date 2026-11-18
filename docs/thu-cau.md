# Thu câu với thời gian tùy chọn

## Tiếp tục sau mất kết nối

Khi đang thu mà COM mất dữ liệu, chương trình bỏ lượt lỗi và hỏi Enter để nối
lại hoặc Q để dừng. Nếu cùng người đeo, chưa tháo găng/chỉnh flex, Enter giữ mốc
flex và chỉ đo lại MPU khi tay yên. Các lượt còn thiếu được tiếp tục tự động,
lưu vào phiên mới có `resumed_from`; dữ liệu phiên trước không bị ghi đè.

Nếu chương trình đã thoát, chạy:

```powershell
.\chay-thu-cau.cmd --user-id U02 --serial-port COM3 --reuse-flex
```

Lệnh này dùng mốc flex gần nhất của U02 trong dữ liệu câu, vẫn khởi tạo MPU mới.
Nhập lại tên câu, thời lượng và **số lượt còn thiếu**, không phải toàn bộ số lượt
cũ. Nếu đã đổi người, tháo găng hoặc chỉnh cảm biến, bỏ `--reuse-flex` để hiệu
chuẩn mới. Cơ chế nối lại không sửa được cáp/nguồn bị chập chờn; không lưu dữ liệu
đứt đoạn hoặc bù mẫu giả.

MPU đã được nâng lên ±4g và ±500°/giây. Để dùng phạm vi mới, đóng các chương
trình COM rồi nạp lại `mophong_com/mophong_com.ino` bằng Arduino IDE (COM3).
Sau khi nạp, đóng Serial Monitor và chạy thu lại, hiệu chuẩn phiên mới.
Python nhận thông báo phạm vi từ firmware; cuối hiệu chuẩn phải hiện
`MPU: +/-4g, +/-500 do/s`. Firmware cũ không thông báo thì giữ kiểm tra ±2g/±250,
không tự nới ngưỡng. Dữ liệu cũ giữ phạm vi trong metadata gốc.

Đóng nhận diện/Serial Monitor trước khi dùng COM3. Từ terminal ở thư mục dự án:

```powershell
.\chay-thu-cau.cmd
```

Mặc định người U2, COM3, 10 lượt. Đổi người hoặc số lượt mặc định:

```powershell
.\chay-thu-cau.cmd --user-id U01 --repetitions 10 --seconds 5
```

1. Hiệu chuẩn cả 5 ngón và MPU theo hướng dẫn, một lần đầu phiên.
2. Nhập tên câu/nhãn, ví dụ `toi cam on ban` (lưu thành `TOI_CAM_ON_BAN`).
   Tên nhãn sau bỏ dấu tối đa 48 ký tự, dùng chữ, số, khoảng trắng hoặc `_`.
3. Nhập thời gian cho câu đó: `3`, `5`, `3s`, `3.5` hoặc `3,5`.
   Cho phép 1–10 giây, bước 0,01 giây. Enter dùng mặc định.
4. Nhập số lượt, hoặc Enter dùng mặc định 10.
5. Chuẩn bị tư thế đầu rồi Enter. Sau đếm ngược 5 giây, khi hiện **BAT DAU**,
   thực hiện trọn câu một lần trong thời gian đã chọn. Nếu xong sớm, giữ tư thế cuối.
6. Sau **HET THOI GIAN**, Enter lưu; R bỏ lượt và thu lại; M bỏ lượt và đổi câu;
   Q bỏ lượt và dừng. Nếu chưa làm xong cả câu, không lưu lượt bị cắt.
7. Hết số lượt, nhập câu tiếp theo. `/Q` ở menu nhập nhãn kết thúc phiên.

Câu khác có thể chọn thời gian khác trong cùng phiên. Nhập lại cùng nhãn sẽ thu
thêm lượt vào cùng CSV, giữ thời gian đã chọn để tránh trộn cấu hình. Muốn đổi
thời gian của cùng nhãn, kết thúc rồi chạy phiên mới. `NONE` cũng được nhập như
một nhãn và chọn thời gian; thu nghỉ/chuyển tay/câu làm dở, không gán câu đúng trọn
vẹn thành NONE. Không có bước chọn tĩnh/động: đây là chế độ thu cả chuỗi câu.

Dữ liệu lưu riêng, không ghi vào dữ liệu chữ/từ cũ:

```text
SmartSignLanguage/phrase_data_5_100hz/
└── U2/
    └── thư mục phiên thu/
        ├── toi_cam_on_ban.csv
        ├── none.csv
        └── imu_reference.json
```

CSV giữ đủ 26 cột (5 flex, MPU, thông tin người/phiên/lượt/nhãn). Mỗi lượt 3 giây
có 300 mẫu thật; 5 giây có 500 mẫu thật, ở 100 Hz. `imu_reference.json` lưu mốc
hiệu chuẩn và `label_settings` gồm thời gian, số mẫu, tên hiển thị từng câu.
Lượt lỗi/mất mẫu/sát biên không được tự bù mẫu để lưu. Mất kết nối vẫn giữ các
lượt đã lưu; chạy lại tạo phiên mới. Firmware USB + Wi-Fi hiện tại dùng được,
không cần nạp lại chỉ để đổi thời gian thu.

## Train và thử nhận diện câu

```powershell
.\train-cau.cmd
.\chay-nhan-dien-cau.cmd --recalibrate
```

Train mặc định dùng toàn bộ dữ liệu câu, không chia test (không có điểm accuracy
mới). Model có tiền tố `phrase_5_100hz_`, không thay thế model chữ/từ.
Đóng chương trình thu và Serial Monitor để giải phóng COM3 trước khi nhận diện.
Nếu vẫn đeo găng và chưa đổi vị trí cảm biến, có thể bỏ `--recalibrate` để dùng
mốc flex mới nhất của U02; MPU vẫn khởi tạo khi giữ tay yên. Người khác dùng
`--user-id U01` và nên hiệu chuẩn mới.

Nhận diện tự động theo lượt: giữ tay nghỉ ổn định khoảng 0,7 giây để chương trình
báo SAN SANG, rồi đưa tay lên thực hiện cả câu như lúc thu. Chuyển động kích hoạt
thu mới; câu 3 giây phải chờ đủ ít nhất 3 giây từ lúc phát hiện mới gọi model.
Không dùng mẫu nghỉ cũ để lấp đầy cửa sổ, không phân loại khi tay đang nghỉ.
Trong lúc thực hiện chỉ hiện DANG THU CAU. Sau kết quả, phải giữ tay ổn định lại
trước lượt mới. Mất mẫu hoặc cảm biến sát biên thì bỏ lượt.

Đây là lấy đoạn thời gian cố định sau khi phát hiện chuyển động, chưa tự hiểu
lúc người dùng đã hoàn thành câu. Nếu làm chậm hơn lúc thu, vẫn có thể thiếu cuối
câu. Ngưỡng chuyển động là cấu hình thử, không chứng minh ký hiệu đúng. Chưa có
phát âm thanh. Nếu có nhiều thời lượng thì chờ thời lượng dài nhất, xét các đoạn
cùng điểm bắt đầu; có xung đột nhãn dương thì chờ. Chương trình giữ dữ liệu raw nguyên vẹn;
chỉ nội suy đặc trưng về 300 điểm thời gian tương đối cho SVM. Train và dự đoán
dùng cùng xử lý flex, gyro, gia tốc. Chưa phải DTW hoặc mô hình dịch câu tự do.

Kiểm tra kết nối nhanh, không đánh giá đúng/sai câu:

Nếu nhận diện đang chạy gặp gói RAW5_100 hỏng hoặc mất kết nối, chương trình bỏ câu
đang thực hiện và thử mở lại COM tối đa 3 lần trong một lần chạy. Giữ tay yên khi
được yêu cầu khởi tạo lại MPU; mốc flex được giữ nguyên, không cần gập/duỗi lại.
Chờ báo SAN SANG rồi thực hiện lại cả câu. Nếu vẫn lỗi sau 3 lần phục hồi, chương
trình dừng để kiểm tra cáp USB, cổng USB và nguồn. Cơ chế này phục hồi phần mềm,
không sửa được nguyên nhân làm hỏng byte trên đường truyền.

```powershell
.\.bridge-venv\Scripts\python.exe .\SmartSignLanguage\predict_phrase_5.py --check-connection
```
