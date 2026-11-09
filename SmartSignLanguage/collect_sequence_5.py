"""Calibrate 3V3/flex/10k-to-GND; collect 150-sample gestures at 100 Hz."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import time
import uuid
import unicodedata

import numpy as np

if __package__:
    from .collect_v2 import SampleStream
    from .serial_transport import SerialTransport
    from .session_folder import folder_name, user_folder
    from .session_csv import label_filename
    from .collect_sequence import valid_label, save_trial
    from .sensor_pipeline import make_imu_reference
    from .five_finger import (CSV_COLUMNS, FLEX_COLUMNS, FLEX_PINS, FINGERS, CALIBRATION_SCHEMA,
                              make_finger_calibration, validate_reference, trial_quality)
else:
    from collect_v2 import SampleStream
    from serial_transport import SerialTransport
    from session_folder import folder_name, user_folder
    from session_csv import label_filename
    from collect_sequence import valid_label, save_trial
    from sensor_pipeline import make_imu_reference
    from five_finger import (CSV_COLUMNS, FLEX_COLUMNS, FLEX_PINS, FINGERS, CALIBRATION_SCHEMA,
                             make_finger_calibration, validate_reference, trial_quality)

BASE = Path(__file__).resolve().parent


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    parser.add_argument("--serial-port", help="USB COM port, e.g. COM5; requires mophong_com firmware at 230400 baud")
    parser.add_argument("--user-id", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--labels", nargs="+", type=valid_label, default=["A", "B", "C", "D", "NONE"])
    group.add_argument("--label", type=valid_label, help="Collect one label only in this session")
    group.add_argument("--interactive-labels", action="store_true", help="Type each word and choose static/dynamic during collection")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--gesture-type", choices=("auto", "static", "dynamic"), default="auto")
    parser.add_argument("--output-dir", type=Path, default=BASE/"sequence_data_5_100hz")
    parser.add_argument("--calibrate-only", action="store_true", help="Check all five sensors and save measured endpoints")
    parser.add_argument("--watch-flex", action="store_true", help="Show all five raw ADC channels live; no calibration or dataset writes")
    return parser


def countdown():
    for number in (5, 4, 3, 2, 1):
        print(number, flush=True)
        time.sleep(1)


def gesture_type(label, mode):
    if label == "NONE":
        return "background"
    return ("dynamic" if label in ("J", "Z") else "static") if mode == "auto" else mode


def gesture_instruction(label, mode):
    kind = gesture_type(label, mode)
    if kind == "background":
        return "NONE: tu the nghi/chuyen dong tu nhien, khong tao dung chu da chon."
    if kind == "dynamic":
        detail = {"J": "Chuan bi hinh I, ngon UT ve net J", "Z": "Chuan bi ngon TRO ve net Z"}.get(label, "Chuan bi tu the dau")
        return f"{label} - DONG: {detail}. Cho BAT DAU moi lam MOT lan trong 1.5s; xong giu tu the cuoi."
    return f"{label} - TINH: tao ky hieu TRUOC khi het dem nguoc; giu yen suot 1.5s thu."


def prompt(message, allowed=("", "Q")):
    while True:
        command = input(message).strip().upper()
        if command in allowed:
            return command
        print("Lua chon khong hop le")


def capture_stable_pose(stream):
    print("GIU YEN 3 giay (1s on dinh + 2s do)...", flush=True)
    rows = stream.capture(3)
    boundary = rows[-1]["timestamp"]-2000
    return [r for r in rows if r["timestamp"] >= boundary]


def normalize_word(value):
    value = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    label = valid_label(re.sub(r"\s+", "_", value.strip()))
    label_filename(label)
    if label == "SAMPLES":
        raise ValueError("SAMPLES la ten danh rieng cho du lieu cu; hay chon ten khac")
    return label


def interactive_labels(reference, folder):
    while True:
        word = input("Nhap tu muon thu (vd: xin chao), NONE: nen | /Q: dung > ").strip()
        if word.upper() == "/Q":
            return
        try:
            label = normalize_word(word)
        except ValueError as error:
            print(f"Nhan khong hop le: {error}")
            continue
        print(f"Nhan luu: {label} -> {label_filename(label)}")
        if label not in reference["labels"]:
            mode = "background" if label == "NONE" else (
                "static" if prompt("D: dong | T: tinh > ", ("D", "T")) == "T" else "dynamic")
            reference["labels"].append(label)
            reference["gesture_types"][label] = mode
            reference.setdefault("label_display_names", {})[label] = word
            (folder/"imu_reference.json").write_text(json.dumps(reference, indent=2), encoding="utf-8")
        yield label


def calibrate(stream):
    calibration = {}
    names = ("CAI", "TRO", "GIUA", "AP UT", "UT")
    print("HIEU CHUAN CA 5 NGON CUNG LUC: DUOI ca ban tay, sau do GAP ca 5 ngon.")
    while True:
        if prompt("DUOI CA 5 NGON thoai mai. ENTER: do | Q: dung > ") == "Q":
            return None
        countdown()
        opened = capture_stable_pose(stream)
        print("GAP CA 5 NGON; gap ca khop ngon CAI de flex cong, khong chi ep ngang long ban tay.")
        print("Nam tay vua phai, khong be nep flex hoac keo cang day.")
        if prompt("GAP CA 5 NGON va giu yen. ENTER: do | Q: dung > ") == "Q":
            return None
        countdown()
        closed = capture_stable_pose(stream)
        calibration = {}
        for key, name, pin in zip(FLEX_COLUMNS, names, FLEX_PINS):
            try:
                c = make_finger_calibration(opened, closed, key)
            except ValueError as error:
                print(f"CHUA DAT {key} ({name}, GPIO {pin}): {error}")
                continue
            calibration[key] = c
            print(f"DAT GPIO {pin}: {c['open']:.0f} -> {c['closed']:.0f}; "
                  f"bien do {c['open']-c['closed']:.0f}; dao dong P90 {c['noise_p90']:.1f}; "
                  f"tach biet {c['open_p05']-c['closed_p95']:.1f} ADC")
            if c['open']-c['closed'] < 60:
                print("Bien do nho nhung hai tu the tach biet. Can kiem tra do lap lai khi thu cu chi that.")
        if len(calibration) == len(FLEX_COLUMNS):
            break
        print("Chua du 5 ngon dat. Chinh ngon/day duoc bao loi; do lai hai tu the DUOI/GAP ca ban tay.")
    if prompt("DUOI tay, dat yen de lay moc MPU. ENTER: tiep tuc | Q: dung > ") == "Q":
        return None
    countdown()
    reference = make_imu_reference(capture_stable_pose(stream), sample_ms=10)
    print("TIEP TUC GIU YEN: khoi tao huong MPU...", flush=True)
    stream.configure_imu(reference)
    stream.capture(2.1)
    if not stream.processor.ready:
        raise ValueError("MPU chua san sang; giu tay yen va thu lai")
    reference.update(flex_pins=FLEX_PINS, fingers=FINGERS, csv_columns=list(CSV_COLUMNS),
                     trial_seconds=1.5, sample_count=150, flex_calibrated=True,
                     flex_calibration_schema=CALIBRATION_SCHEMA, flex_calibration=calibration,
                     flex_calibration_method="all-fingers-3s-last-2s",
                     divider_ohms=10000, supply_volts=3.3,
                     divider_topology="3V3-flex-ADC-10k-GND",
                     collection_protocol="five-flex-calibrated-100hz-1.5s-v2",
                     imu_source="raw MPU6050 + Python complementary filter (not DMP)",
                     imu_ranges={"accel_g": 2, "gyro_deg_s": 250, "dlpf_hz": 21})
    return validate_reference(reference)


def watch_flex(stream):
    print("F1=CAI/32, F2=TRO/33, F3=GIUA/34, F4=AP UT/35, F5=UT/36.")
    print("Duoi/gap RIENG mot ngon, xem kenh nao thay doi. Ctrl+C de dung; khong luu dataset.")
    print("Moi kenh: ADC trung vi [P5..P95] trong cua so 0.4s. Khoang nay gom ca chuyen dong neu dang gap.")
    while True:
        rows = stream.capture(.4)
        parts = []
        for i, key in enumerate(FLEX_COLUMNS):
            values = np.asarray([r[key] for r in rows])
            lo, hi = np.percentile(values, [5, 95])
            bad = int(np.count_nonzero((values <= 8) | (values >= 4087)))
            parts.append(f"F{i+1}={np.median(values):.0f} [{lo:.0f}..{hi:.0f}] "
                         f"min/max={values.min():.0f}/{values.max():.0f} loi={bad}/{len(values)}")
        print(" | ".join(parts), flush=True)


def preview_trial(rows, label, trial_id):
    """Summarize the actual captured window before asking whether to save it."""
    quality = trial_quality(rows)
    print(f"MAU VUA THU: nhan={label}, trial={trial_id}, {len(rows)} mau, {quality['hz']:.2f} Hz")
    print("Flex ADC trung vi [min..max]: " + " | ".join(
        f"F{i+1}={np.median([r[k] for r in rows]):.0f} "
        f"[{min(r[k] for r in rows):.0f}..{max(r[k] for r in rows):.0f}]"
        for i, k in enumerate(FLEX_COLUMNS)))
    sample = rows[0]
    print("Mau dau: timestamp=" + str(sample["timestamp"]) + " ms; " + "; ".join(
        f"{k}={sample[k]:.4f}" for k in ("ACCx", "ACCy", "ACCz", "GYRx", "GYRy", "GYRz")))


def recover_imu(stream, reference, folder, trial_id):
    """Reseed orientation only; preserve the session's flex endpoints and gyro bias."""
    reason = str(stream.recovery_required)
    while True:
        if stream.error:
            raise stream.error
        if prompt("Dat tay YEN de khoi tao lai huong MPU. ENTER: tiep tuc | Q: dung > ") == "Q":
            return False
        try:
            # First collect raw rest data and verify stationarity. Do not replace
            # the reference used by previously saved rows in this session.
            stream.configure_imu(reference)
            print("GIU YEN trong khi khoi tao lai MPU...", flush=True)
            resting = stream.capture(2.1)
            measured = make_imu_reference(resting, sample_ms=10)
            if np.linalg.norm(np.asarray(measured["gyro_bias"])-np.asarray(reference["gyro_bias"])) > .03:
                raise ValueError("Gyro bias da thay doi; dung va tao phien hieu chuan moi")
            if abs(measured["gravity"]-reference["gravity"]) > .3:
                raise ValueError("Moc trong luc da thay doi; dung va tao phien hieu chuan moi")
            if not stream.processor or not stream.processor.ready:
                raise ValueError("MPU chua on dinh")
        except ValueError as error:
            print(f"CHUA PHUC HOI: {error}")
            continue
        event = {"before_trial_id": trial_id, "timestamp": resting[-1]["timestamp"],
                 "action": "orientation_reseed", "gyro_bias_unchanged": True, "reason": reason}
        with (folder/"imu_recovery.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(event)+"\n")
        print("MPU SAN SANG. Giu cac trial da luu; thu lai luot chua luu.")
        return True


def collect_session(args):
    interactive = args.interactive_labels
    labels = [] if interactive else [args.label] if args.label else args.labels
    sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    folder = args.output_dir/user_folder(args.user_id)/folder_name(sid, args.user_id, ["TU_TUY_CHON"] if interactive else labels)
    stream = None
    sock = None
    try:
        serial_port = getattr(args, "serial_port", None)
        if serial_port:
            print(f"Ket noi {serial_port}, 230400 baud; cho ESP32 khoi dong...", flush=True)
            sock = SerialTransport(serial_port)
        else:
            sock = socket.create_connection((args.esp32_host, args.esp32_port), timeout=3)
        stream = SampleStream(sock, flex_count=5, sample_ms=10, recover_collection_gaps=True)
        quality = stream.check_ready()
        print(f"RAW5_100: {quality['hz']:.2f} Hz. GPIO cai/tro/giua/ap-ut/ut = 32/33/34/35/36.")
        if args.watch_flex:
            watch_flex(stream)
            return 0
        reference = calibrate(stream)
        if reference is None:
            return 0
        reference.update(user_id=args.user_id, session_id=sid, labels=labels,
                         repetitions=args.repetitions, gesture_type=args.gesture_type,
                         gesture_types={label: gesture_type(label, args.gesture_type) for label in labels},
                         data_layout="per-label-csv-v1",
                         transport="usb-serial" if serial_port else "tcp",
                         connection=serial_port or args.esp32_host,
                         serial_baud=230400 if serial_port else None)
        folder.mkdir(parents=True, exist_ok=False)
        (folder/"imu_reference.json").write_text(json.dumps(reference, indent=2), encoding="utf-8")
        print(f"Phien moi: {folder}")
        if args.calibrate_only:
            return 0
        print(f"Nguoi thu: {args.user_id} | Nhan: {', '.join(labels)} | {args.repetitions} luot/nhan")
        print("CSV luu du cac cot: " + ", ".join(CSV_COLUMNS))
        print("Moi dong co nhan, ma nguoi/phien/luot; moc hieu chuan luu trong imu_reference.json.")
        if "NONE" not in labels:
            print("LUU Y: phien chi co nhan da chon; de train can them NONE va du nhan o cac phien khac.")
        print("Moi trial: dem nguoc 5s, thu 150 mau that / 1.5s. R: bo va thu lai.")
        print("Tu the TINH: tao dung ky hieu TRUOC khi het dem nguoc, giu trong 1.5s.")
        print("Cu chi DONG: lam tron mot lan khi BAT DAU; khong can duoi tay 0.5s dau.")
        print("NONE: luan phien nghi va cac chuyen dong khong thuoc nhan da chon.")
        trial_id = 1
        counts = Counter()
        for label in interactive_labels(reference, folder) if interactive else labels:
            mode = reference["gesture_types"][label]
            target = counts[label] + args.repetitions
            print(gesture_instruction(label, mode), flush=True)
            while counts[label] < target:
                command = prompt(f"[{label} {counts[label]+1}/{target}] ENTER: chuan bi | Q: dung > ")
                if command == "Q":
                    return 0
                try:
                    stream.check_ready()
                    countdown()
                    try:
                        cursor = stream.start_trial()
                        action = "LAM CHUYEN DONG MOT LAN" if gesture_type(label, mode) == "dynamic" else "GIU KY HIEU" if label != "NONE" else "NGHI / CHUYEN DONG TU NHIEN"
                        print(f"BAT DAU {label} - {action}", flush=True)
                        rows = stream.capture(1.5, sample_count=150, after=cursor)
                    finally:
                        stream.sock.sendall(b"STOP\n")
                    trial_quality(rows)
                except ValueError as error:
                    if stream.error:
                        raise stream.error
                    print(f"BO trial: {error}")
                    if stream.recovery_required and not recover_imu(stream, reference, folder, trial_id):
                        return 0
                    continue
                preview_trial(rows, label, trial_id)
                command = prompt("Da lam dung? ENTER: luu | R: bo/thu lai | Q: bo va dung > ", ("", "R", "Q"))
                if command == "Q":
                    return 0
                if command == "R":
                    continue
                quality = save_trial(folder/label_filename(label), rows, args.user_id, sid, trial_id, label,
                                     columns=CSV_COLUMNS, quality_check=trial_quality)
                counts[label] += 1
                print(f"DA LUU {label}: {counts[label]}/{target}, {quality['samples']} mau, {quality['hz']:.2f} Hz")
                trial_id += 1
        print("DA XONG. Thu lai it nhat mot phien du cac nhan sau khi thao/deo lai gang de danh gia.")
        return 0
    except (OSError, ValueError) as error:
        print(f"LOI: {error}. Trial dang thu KHONG luu; cac trial da luu van con. Chay lai de tao phien moi.")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nDa dung; trial chua hoan tat khong duoc luu.")
        return 0
    except ImportError as error:
        print(f"Thieu thu vien: {error}. Cai pyserial/numpy theo docs/thu-qua-com.md")
        return 1
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()
        if getattr(args, "serial_port", None) and sock:
            print("Da dong COM. Firmware USB + Wi-Fi se noi lai Wi-Fi; khong can nap lai.")
        if folder.exists():
            print(f"DU LIEU PHIEN: {folder}")


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", args.user_id) or args.repetitions < 1:
        print("LOI: user-id chi dung A-Z/a-z/0-9/_/-, 1..40 ky tu; repetitions >= 1")
        return 1
    labels = [] if args.interactive_labels else [args.label] if args.label else args.labels
    try:
        for label in labels:
            label_filename(label)
    except ValueError as error:
        print(f"LOI: {error}")
        return 1
    if len(labels) != len(set(labels)):
        print("LOI: danh sach nhan bi trung")
        return 1
    return collect_session(args)


if __name__ == "__main__":
    raise SystemExit(main())
