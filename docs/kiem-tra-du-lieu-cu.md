# Kiểm tra dữ liệu cũ trước khi chuyển v2

Các CSV gốc giữ nguyên; không sửa timestamp bằng số đoán.

| File | Kết quả |
|---|---|
| `SmartSignLanguage/dataset_gesture.csv` | 1.548 dòng, 30 lượt, 10 lượt/nhãn XIN_CHAO/CAM_ON_NHIEU/NONE. Không thiếu giá trị, NaN/Inf hay dòng trùng hoàn toàn. |
| Cùng file, trial 20 | Dòng 980 time_ms=1, kế tiếp 1147161. Nhảy 1.147.160 ms; cần đối chiếu bản gốc hoặc thu lại. Không sửa tự động. |
| Các khoảng còn lại của gesture | Trung bình 24,99 Hz, khoảng cách mẫu 2–94 ms. |
| `SmartSignLanguage/dataset_sentence.csv` | 538 dòng, 10 lượt DAO_NAY_BAN_KHOE_KHONG, 7,715–10,104 s/lượt, khoảng 5,83 Hz. Không phù hợp trực tiếp cửa sổ 25 Hz/2 giây. |
| `SmartSignLanguage/dataset/dataset.csv` | 2.000 dòng hai flex, 4 nhãn tư thế, thiếu timestamp/trial/session; không tự ghép vào dữ liệu chuỗi. |

Model cũ có CAM_ON_NHIEU, NONE, XIN_CHAO. Thu câu dài vào file khác không tự cập nhật
model. dFlex/dFlexAvg khớp phép tính trong các lượt, trong sai số làm tròn; chưa chứng
minh chúng giúp nhận diện tốt hơn.

Trainer v2 chỉ đọc `data_v2/**/samples.csv` kèm calibration.json. Không đưa các file
cũ thiếu mốc/metadata vào model mới. Chưa có dữ liệu v2 thật cho đến khi người dùng
nạp firmware, hiệu chuẩn và thực hiện các lượt thu trên găng.
