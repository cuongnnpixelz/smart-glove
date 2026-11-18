# Phát câu nhận diện qua ESP32 và MAX98357A

Model ExtraTrees U4+U5 vẫn chạy trên máy tính. ESP32 đọc cảm biến và phát âm
thanh; chưa chuyển model xuống ESP32. Cần duy trì USB với máy tính.

Luồng hoạt động: cử chỉ → Python chốt câu → tạo giọng tiếng Việt → gửi âm thanh
qua COM → ESP32 giải mã → I2S → MAX98357A → loa 4Ω–2W.
Không phát các nhãn cửa sổ tạm thời hoặc kết quả rỗng/NONE. Khi phát xong,
chương trình bỏ các mẫu trong lúc chờ/phát tiếng và chờ tay yên để làm câu mới.
Chế độ kiểm tra câu đọc **máy đoán**, không đọc câu đúng do bạn nhập.

## Nối dây

| ESP32 | MAX98357A |
|---|---|
| GPIO 18 | BCLK |
| GPIO 19 | LRC / LRCLK |
| GPIO 23 | DIN |
| GND | GND |
| Nguồn 3,3V hiện tại; module cũng hỗ trợ nguồn 5V ổn định | VIN |

Hai dây loa nối vào hai cọc **+ và − đầu ra loa** trên module. Không nối cọc
âm loa xuống GND. Giữ cấu hình SD/GAIN đang dùng khi test thành công; GAIN
để hở thường là 9 dB. Các chân flex, MPU và LCD giữ nguyên.

Bạn đã xác nhận VIN đang cấp **3,3V**, GAIN để hở. Loa là **4Ω–2W**;
chip có thể vượt 2W ở nguồn 5V. Firmware mới chia biên độ âm thanh cho **2**,
thay cho chia 4: biên độ tăng gấp đôi (+6 dB) với cùng file và mức Python.
Điều này không có nghĩa tai nghe thấy to gấp đôi hoặc loa đang phát 2W.
Python mặc định còn nhân 0,7. Thử `--speech-volume 1.0` sau khi nạp bản mới.
Giới hạn trong code
**không phải phép đo hay bộ khống chế chính xác công suất 2W**. Nếu rè thì giảm
`--speech-volume 0.4`; không tăng GAIN để ép loa to. Giới hạn `--speech-volume`
là lớn hơn 0 và không quá 1, tương đối với mức đã hạn chế trong firmware.

## Nạp firmware một lần

Đóng chương trình đang dùng COM và Serial Monitor. Trong thư mục dự án:

```powershell
.\nap-firmware-co-loa.ps1 -Port COM3
```

Nếu PowerShell chặn `.ps1`, chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\nap-firmware-co-loa.ps1" -Port COM3
```

Hoặc mở `mophong_com/mophong_com.ino` trong Arduino IDE, chọn **ESP32 Dev Module**,
đúng cổng COM rồi Upload. File `glove_audio.h` cần nằm cùng thư mục sketch.
Đã biên dịch với Arduino-ESP32 **2.0.14**, dùng API `driver/i2s.h` tương ứng.
Không nạp riêng sketch phát tiếng bíp: sketch tích hợp đã gồm cả cảm biến và loa.

## Python và chạy thử

Các thư viện đã được cài trong Python 3.10 dùng cho lượt triển khai này. Nếu
chạy Python/môi trường khác, cài vào đúng môi trường đó:

```powershell
python -m pip install -r SmartSignLanguage/requirements-speech.txt
```

Test đường tiếng độc lập, không cần làm cử chỉ:

```powershell
python -m SmartSignLanguage.esp32_speech --serial-port COM3
```

Loa phải nói “Xin chào. Tôi cảm ơn bạn.”. `AUDIO_DONE` chỉ xác nhận ESP32 đã
đưa âm thanh qua I2S; phần mềm không đo được loa có đấu đúng hay nghe rõ không.

Nhận diện câu và phát tiếng:

```powershell
python -m SmartSignLanguage.predict_sentence_words --serial-port COM3 --min-votes 5 --none-windows 10 --speak
```

Cũng có thể mở `chay-ghep-cau-co-loa.cmd`. Không thêm `--seconds 5` nếu muốn
kết thúc theo 10 NONE. Giữ các ngoại lệ TÊN 2 cửa sổ, CẢM ƠN 1 cửa sổ và bộ lọc
ngữ cảnh đang dùng. Âm thanh đọc kết quả bộ lọc, không tự sửa câu nhận nhầm.

Nhập câu đúng, làm cử chỉ, nghe kết quả và lưu thống kê:

```powershell
python -m SmartSignLanguage.check_sentence_words --serial-port COM3 --min-votes 5 --none-windows 10 --speak
```

## Internet và độ trễ

Mặc định dùng `gTTS` tiếng Việt (`google-vi`): **chỉ văn bản câu kết quả** được
gửi đến dịch vụ Google để tạo giọng; không gửi dữ liệu cảm biến. Máy tính cần
Internet cho câu chưa có trong bộ nhớ đệm. ESP32 không cần Wi-Fi trong chế độ COM.
Âm thanh được lưu theo câu/giọng/âm lượng ở `.runtime/speech_cache`; câu lặp
lại dùng bản lưu, không gọi dịch vụ. Câu mới có độ trễ tùy mạng/dịch vụ.

Đã tạo thành công tiếng Việt bằng gTTS trên máy này. Giọng Edge tùy chọn
(`--speech-voice vi-VN-HoaiMyNeural`) có trong danh sách dịch vụ nhưng không trả
âm thanh khi kiểm tra, nên không chọn làm mặc định.

Lỗi mạng/loa được báo riêng, không sửa hoặc xóa kết quả nhận diện. Không tự phát
lại khi mất xác nhận để tránh đọc câu hai lần. Nếu mất gói cảm biến, các kiểm
tra cảm biến cũ vẫn có hiệu lực; âm thanh không được dùng để che lỗi cảm biến.

Có thể kiểm tra loa không cần Internet bằng file WAV/MP3 có sẵn:

```powershell
python -m SmartSignLanguage.esp32_speech --serial-port COM3 --audio-file "C:\duong-dan\cau-noi.wav"
```

## Giao thức và kiểm chứng

- USB vẫn **230400 baud**, RAW5_100 gửi 100 Hz như cũ.
- Âm thanh mono 16 kHz mã hóa μ-law: 16 kB/s, phù hợp băng thông USB-UART.
  ESP32 giải mã thành PCM 16-bit và nhân đôi sang L/R, I2S 16 kHz.
- `AUDIO_HELLO` → `AUDIO_READY,1,16000,1024` kiểm tra firmware.
- `AUDIO_BEGIN,id` → `AUDIO_STARTED,id`.
- `AUDIO_DATA,id,sequence,length,crc32_hex\n` + đúng `length` byte nhị phân.
  Tối đa 1024 byte/gói. Firmware kiểm tra thứ tự, CRC và dung lượng rồi ACK.
  Python gửi cả header và payload trong một khóa ghi để PING không chen vào.
- `AUDIO_END,id,count` → `AUDIO_DONE,id` sau khi đẩy hết tiếng qua DMA.
- Bộ đệm hữu hạn, timeout và `AUDIO_ABORT,id` xử lý truyền bị ngắt. Chỉ một
  luồng Python đọc COM; ACK được tách khỏi dữ liệu cảm biến. Worker I2S không
  ghi Serial, tránh trộn dòng cảm biến và phản hồi.
- Câu âm thanh tối đa dưới 60 giây; câu quá dài báo lỗi, không phát bản bị cắt.

Nguồn đối chiếu: [MAX98357A – Analog Devices](https://www.analog.com/en/products/max98357a.html),
[ESP-IDF I2S](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32/api-reference/peripherals/i2s.html),
[gTTS](https://gtts.readthedocs.io/en/v2.5.1/module.html).
