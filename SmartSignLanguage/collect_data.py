import serial
import csv
import os
import time
import sys

# ============================================================
# CẤU HÌNH
# ============================================================

SERIAL_PORT = "COM3"      # Đổi nếu COM của bạn khác
BAUD_RATE = 115200

CSV_FILE = "dataset_gesture.csv"

# Thời gian thu mỗi cử chỉ
RECORD_SECONDS = 2.0

# Số trường mà ESP32 đang gửi
EXPECTED_SENSOR_FIELDS = 13

# ============================================================
# CỘT SENSOR TỪ ESP32
# ============================================================

SENSOR_COLUMNS = [
    "time_ms",
    "flex1",
    "flex2",
    "dFlex1",
    "dFlex2",
    "dFlex1Avg",
    "dFlex2Avg",
    "ax",
    "ay",
    "az",
    "gx",
    "gy",
    "gz"
]

CSV_COLUMNS = [
    "trial_id",
    "label"
] + SENSOR_COLUMNS


# ============================================================
# TẠO FILE CSV
# ============================================================

def prepare_csv():

    if not os.path.exists(CSV_FILE):

        with open(
            CSV_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)

        print(f"[OK] Da tao file: {CSV_FILE}")

    else:

        print(f"[OK] File da ton tai: {CSV_FILE}")


# ============================================================
# LẤY trial_id TIẾP THEO
# ============================================================

def get_next_trial_id():

    if not os.path.exists(CSV_FILE):
        return 1

    max_trial = 0

    try:

        with open(
            CSV_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                try:

                    trial = int(row["trial_id"])

                    if trial > max_trial:
                        max_trial = trial

                except:
                    pass

    except Exception as e:

        print("[LOI] Khong doc duoc dataset:", e)

    return max_trial + 1


# ============================================================
# ĐỌC 1 DÒNG SENSOR
# ============================================================

def read_sensor_line(ser):

    try:

        raw = ser.readline()

        if not raw:
            return None

        line = raw.decode(
            "utf-8",
            errors="ignore"
        ).strip()

        if not line:
            return None

        # Bỏ qua header ESP32
        if line.startswith("time_ms"):
            return None

        # Bỏ qua các thông báo khác
        if "LOI" in line:
            return None

        if "HE THONG" in line:
            return None

        if "MPU" in line:
            return None

        parts = line.split(",")

        if len(parts) != EXPECTED_SENSOR_FIELDS:
            return None

        # Kiểm tra dữ liệu có phải số không
        try:

            float(parts[0])

            for value in parts[1:]:
                float(value)

        except ValueError:
            return None

        return parts

    except Exception:
        return None


# ============================================================
# ĐẾM NGƯỢC
# ============================================================

def countdown():

    print()
    print("Chuan bi...")

    for i in range(3, 0, -1):

        print(i)
        time.sleep(1)

    print("BAT DAU!")


# ============================================================
# THU 1 TRIAL
# ============================================================

def record_trial(ser, label, trial_id):

    # --------------------------------------------------------
    # ĐẾM NGƯỢC TRƯỚC
    # --------------------------------------------------------

    countdown()

    # --------------------------------------------------------
    # QUAN TRỌNG:
    # Xóa toàn bộ dữ liệu đã sinh ra trong lúc 3-2-1
    # --------------------------------------------------------

    ser.reset_input_buffer()

    time.sleep(0.02)

    samples = []

    start_time = time.perf_counter()

    # --------------------------------------------------------
    # THU ĐÚNG RECORD_SECONDS
    # --------------------------------------------------------

    while (time.perf_counter() - start_time) < RECORD_SECONDS:

        data = read_sensor_line(ser)

        if data is not None:
            samples.append(data)

    print("KET THUC!")

    # --------------------------------------------------------
    # KIỂM TRA DỮ LIỆU
    # --------------------------------------------------------

    if len(samples) == 0:

        print("[LOI] Khong thu duoc mau nao.")
        return False

    # --------------------------------------------------------
    # GHI VÀO FILE
    # --------------------------------------------------------

    try:

        with open(
            CSV_FILE,
            "a",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.writer(f)

            for sample in samples:

                writer.writerow(
                    [trial_id, label] + sample
                )

    except Exception as e:

        print("[LOI] Khong ghi duoc file:")
        print(e)

        return False

    # --------------------------------------------------------
    # THÔNG BÁO
    # --------------------------------------------------------

    print(
        f"[OK] Trial {trial_id} | "
        f"Label: {label} | "
        f"So mau: {len(samples)}"
    )

    # Kiểm tra sơ bộ số mẫu
    if len(samples) < 40:

        print(
            "[CANH BAO] So mau hoi thap. "
            "Neu ESP32 dang 25Hz thi 2 giay nen gan 50 mau."
        )

    elif len(samples) > 65:

        print(
            "[CANH BAO] So mau cao bat thuong. "
            "Kiem tra tan so gui cua ESP32."
        )

    else:

        print("[OK] So mau hop ly.")

    return True


# ============================================================
# HIỂN THỊ HƯỚNG DẪN
# ============================================================

def print_instructions():

    print()
    print("==============================================")
    print(" THU DATA GANG TAY NHAN DIEN CU CHI")
    print("==============================================")
    print()

    print("Quy tac:")
    print("- ENTER : thu 1 trial")
    print("- C     : doi ky hieu")
    print("- Q     : thoat")
    print()

    print("Luu y:")
    print("- Dong Serial Monitor cua Arduino IDE.")
    print("- Khong cho Arduino va Python mo COM cung luc.")
    print("- Khi BAT DAU hien ra thi moi thuc hien cu chi.")
    print("- Cho Flex ve moc duoi on dinh; neu khong hoi, kiem tra cam bien/cach gan.")
    print("- Day la bo thu LEGACY. Du lieu moi: dung collect_v2.py.")
    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print_instructions()

    prepare_csv()

    # --------------------------------------------------------
    # MỞ SERIAL
    # --------------------------------------------------------

    try:

        ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=0.1
        )

    except Exception as e:

        print()
        print("[LOI] Khong mo duoc Serial.")
        print(e)

        print()
        print("Kiem tra:")
        print(f"- ESP32 co dung {SERIAL_PORT} khong")
        print("- Serial Monitor da dong chua")
        print("- Cap USB co ket noi khong")
        print("- Baud ESP32 co phai 115200 khong")

        return

    print()
    print(f"[OK] Da ket noi ESP32: {SERIAL_PORT}")

    # ESP32 có thể reset khi mở COM
    time.sleep(2)

    # Xóa dữ liệu khởi động ESP32
    ser.reset_input_buffer()

    trial_id = get_next_trial_id()

    print(f"[OK] Trial tiep theo: {trial_id}")

    # --------------------------------------------------------
    # VÒNG LẶP CHÍNH
    # --------------------------------------------------------

    while True:

        print()
        print("----------------------------------------------")

        label = input(
            "Nhap ten ky hieu "
            "(VD XIN_CHAO, CAM_ON_NHIEU, NONE) "
            "hoac Q de thoat: "
        ).strip().upper()

        if label == "Q":
            break

        if label == "":
            print("[LOI] Ten ky hieu khong duoc rong.")
            continue

        # Khuyến nghị dùng dấu _
        label = label.replace(" ", "_")

        print()
        print(f"Ky hieu dang thu: {label}")

        # ----------------------------------------------------
        # THU NHIỀU TRIAL CÙNG LABEL
        # ----------------------------------------------------

        while True:

            print()
            print(
                f"Nhan ENTER de thu "
                f"{label} - trial {trial_id}"
            )

            print("Nhap C de doi ky hieu.")
            print("Nhap Q de thoat.")

            command = input("> ").strip().upper()

            if command == "C":
                break

            if command == "Q":

                ser.close()

                print()
                print("Da dong Serial.")
                print("Ket thuc chuong trinh.")

                return

            success = record_trial(
                ser,
                label,
                trial_id
            )

            if success:
                trial_id += 1

    # --------------------------------------------------------
    # ĐÓNG SERIAL
    # --------------------------------------------------------

    ser.close()

    print()
    print("Da dong Serial.")
    print(f"Dataset: {CSV_FILE}")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print("Dung chuong trinh bang ban phim.")

        sys.exit(0)
