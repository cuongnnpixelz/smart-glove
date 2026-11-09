# Dùng găng tay nhận diện liên tục

Chạy Python một lần; **không nhấn Enter cho từng cử chỉ**, không cần web.
ESP32 đọc cảm biến và hiện LCD; máy tính chạy model. Mang ra ngoài vẫn cần
máy tính chạy Python và mạng kết nối với ESP32. Model chưa chạy độc lập trên ESP32.

## Nạp một firmware dùng chung

1. Dừng chương trình Python đang nối găng bằng Ctrl+C.
2. Mở `mophong_wireless/mophong_wireless.ino` trong Arduino IDE.
3. Chọn đúng board ESP32 và cổng của găng, bấm Upload.
4. Xem IP ESP32, đóng Serial Monitor. Firmware này có cả `RAW2`, `SEQ` và `RUN`.

Không tạo bản `.ino` khác cho thu dữ liệu. Chương trình thu gửi RAW2/START/STOP;
chương trình sử dụng gửi RAW2/RUN/SEQ. Nhịp lấy mẫu và cách đọc cảm biến dùng chung.
Không cần train lại để bật luồng liên tục, nhưng độ chính xác cần kiểm tra lại thực tế.

## Chạy

Tại `C:\Users\Admin\Downloads\newbie4`:

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\predict_continuous.py --esp32-host 192.168.137.115
```

Hoặc `powershell -ExecutionPolicy Bypass -File .\chay-nhan-dien-chuoi.ps1`.
Thay IP nếu đổi mạng. Mặc định chọn model v2 mới nhất và in đường dẫn;
dùng `--model <thu-muc-model>` nếu muốn chọn cụ thể.

| LCD | Bạn làm gì? |
|---|---|
| `DANG LAY MOC MPU` / `DUOI TAY GIU YEN` | Duỗi hai ngón, đặt tay yên khoảng 4 giây. Nếu còn chuyển động, chương trình tự thử lấy mốc lại. |
| `CHO TAY NGHI` / `DUOI VA GIU YEN` | Đưa cổ tay về giữa, duỗi ngón, chờ ổn định. |
| `SAN SANG` / `HAY LAM CU CHI` | Bắt đầu một chuỗi, không bấm phím. |
| `DANG NHAN DIEN` / `LAM TRON CHUOI` | Làm hết chuỗi, không bắt đầu chuỗi thứ hai ngay. |
| `XIN CHAO`, `CAM ON`, `TAM BIET` / `DUOI DE TIEP` | Kết quả vừa nhận. Duỗi/giữ yên, chờ SAN SANG để làm tiếp. |
| `CHUA NHAN DIEN` | Cửa sổ bị từ chối hoặc model trả NONE. Về tư thế nghỉ để thử lại. |

Ánh xạ giữ nguyên:

- `TRO_TRAI_DUOI` → `XIN CHAO`.
- `GIUA_TRAI_DUOI` → `CAM ON`.
- `TRO_PHAI_DUOI` → `TAM BIET`.

Giữ ngón còn lại duỗi; gập ngón đúng → nghiêng → cổ tay về giữa → mới duỗi ngón.
Hoàn tất động tác trong khoảng thời gian đã thu (cửa sổ model 5 giây).
Giữa hai lượt, duỗi và giữ yên ít nhất khoảng 1,5 giây, chờ LCD SAN SANG.
ADC được phép hồi chưa hết; vẫn cần có biến thiên hồi đo được, không giữ nguyên tư thế gập.
Ctrl+C trong terminal để dừng.

## Cách xử lý và giới hạn

- Luôn nhận mẫu 25 Hz. Chuyển động flex hoặc gyro kích hoạt một cửa sổ;
  giữ khoảng 0,6 giây dữ liệu trước điểm kích hoạt để có nền ban đầu.
- Cửa sổ dài đủ 5 giây thật, không kéo giãn/padding. Chỉ suy luận một lần mỗi
  cửa sổ đã kích hoạt, không cắt luồng thành các khối 5 giây cố định.
- Trước khi hiện kết quả, kiểm tra có gập/hồi, cổ tay quay về gần tư thế đầu và
  cuối cửa sổ tương đối yên. Với ba nhãn trên, kiểm tra flex tương ứng: trỏ=flex_2,
  giữa=flex_1. Theo mạch đã đo, ADC giảm khi gập. Nếu đổi dây/cảm biến cần sửa ánh xạ.
- Không yêu cầu ADC cuối bằng đúng ADC đầu. Không phát lặp một tư thế giữ nguyên;
  chờ hồi/nghỉ trước khi cho phép cửa sổ tiếp theo.
- Gián đoạn trên 120 đến 500 ms khi đang nhận diện: giữ TCP, bỏ chuỗi đang xét,
  LCD về `CHO TAY NGHI`. Giữ nguyên gyro bias/trọng lực đã đo; bỏ hướng cũ, chờ
  khoảng 800 ms dữ liệu mới liên tục và ổn định rồi khởi tạo lại hướng từ đoạn
  nghỉ đó. Nếu tay còn chuyển động hoặc lại gián đoạn, thời gian chờ kéo dài.
  Không tích phân gyro qua thời gian bị thiếu và không ghép đoạn trước/sau lỗi.
- Gián đoạn trên 500 ms, timestamp reset, dữ liệu hỏng, tràn hàng đợi hoặc mất
  kết nối vẫn bỏ chuỗi và khởi tạo lại đầy đủ. Đây là ngưỡng phục hồi của demo,
  không phải giới hạn phần cứng. Khi mới khởi động/lấy mốc đầu tiên, vẫn kiểm tra nghiêm.
- Cơ chế phục hồi nhanh chỉ bật trong `predict_continuous.py` sau khi lấy mốc
  ban đầu. Bộ thu dữ liệu vẫn loại khoảng trống trên 120 ms như trước. Luồng
  runtime phục hồi không được dùng để ghi cửa sổ huấn luyện.
- Heartbeat chạy trong cùng vòng xử lý. ESP32 xóa trạng thái/kết quả cũ nếu Python
  im lặng quá 6 giây; ngắt kết nối cũng xóa trạng thái cũ.

Đây là bước chuyển từ test từng lượt sang tự động, **chưa phải model đã được
đánh giá trên chuỗi liên tục thực tế**. Cửa sổ 5 giây có thể bỏ sót động tác quá
nhanh/chậm hoặc hai động tác nối liền không nghỉ. Các ngưỡng phân đoạn là quy tắc
demo. Model classifier-only vẫn chưa bảo đảm phát hiện mọi trường hợp sai thứ tự
hoặc cả hai ngón gập; kiểm tra gập/hồi bổ sung không thay thế dữ liệu NONE đa dạng.
Điểm test 94,7% trước đây chỉ áp dụng các trial tách sẵn trong phiên.

Để kiểm tra: thử mỗi chuỗi đúng 10 lần; thêm chỉ nghiêng, chỉ gập, giữ gập lâu,
thả ngón sớm và lặp lại cùng chuỗi sau khi nghỉ. Ghi số lần nhận đúng, bỏ sót,
nhận nhầm, phát lặp và thời gian chờ. Nếu cần nhận chuỗi nối liền tự nhiên, cần
thu thêm bản ghi liên tục có nhãn mốc bắt đầu/kết thúc và đánh giá lại cách phân đoạn.

## Thu thêm dữ liệu vẫn dùng chương trình riêng

```powershell
.\.bridge-venv\Scripts\python.exe SmartSignLanguage\collect_sequence_v2.py --user-id U01 --esp32-host 192.168.137.115 --manual-labels --label TRO_TRAI_DUOI
```

Dừng nhận diện liên tục trước khi thu. Chế độ thu vẫn hỏi nhãn và xác nhận lưu,
không thay đổi dataset khi chỉ đang sử dụng. `predict_sequence_v2.py` được giữ
như công cụ kiểm tra một lượt có Enter; launcher sử dụng đã chuyển sang liên tục.
