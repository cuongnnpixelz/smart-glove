"""Simple collector for NEW two-flex + MPU gesture labels.

Stores raw measurements plus estimated quaternion and linear acceleration.
One trial contains the entire movement sequence under one label.
"""
import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import re
import socket
import time
import uuid

if __package__:
    from .collect_v2 import SampleStream
    from .sensor_pipeline import CSV_COLUMNS, Q_COLUMNS, SamplingGap, make_imu_reference, timing_report
else:
    from collect_v2 import SampleStream
    from sensor_pipeline import CSV_COLUMNS, Q_COLUMNS, SamplingGap, make_imu_reference, timing_report

BASE = Path(__file__).resolve().parent
COLUMNS = CSV_COLUMNS
SENSOR_COLUMNS = tuple(k for k in COLUMNS if k not in ("user_id", "session_id", "trial_id", "label"))

# Alternate real positives and hard negatives within the SAME recording session.
NEGATIVE_STEPS = (
    ("CHI_NGHIENG", "Hai ngon DUOI, chi nghieng dung huong roi ve giua; KHONG gap"),
    ("CHI_GAP", "Gap CA HAI ngon roi duoi; giu co tay yen, KHONG nghieng"),
    ("SAI_HUONG", "Gap hai ngon -> nghieng HUONG NGUOC lai -> ve giua -> duoi"),
    ("THA_SOM", "Gap -> nghieng -> DUOI KHI CON NGHIENG -> moi ve giua"),
    ("MOT_NGON", "Chi gap MOT ngon -> nghieng dung huong -> ve giua -> duoi; luan phien tro/giua"),
    ("NGHI", "Duoi hai ngon, giu yen toan bo 5 giay"),
)


def demo_step(index, positive_label):
    if index % 2 == 0:
        return positive_label, "DUNG_CHUOI", "Gap CA HAI ngon -> giu gap/nghieng DUNG HUONG -> ve giua -> moi duoi"
    subtype, instruction = NEGATIVE_STEPS[(index//2) % len(NEGATIVE_STEPS)]
    return "NONE", subtype, instruction


def valid_label(value):
    value = value.strip().upper().replace(" ", "_")
    if not re.fullmatch(r"[A-Z0-9_]{1,48}", value):
        raise ValueError("Nhan chi dung A-Z, 0-9, dau gach duoi; toi da 48 ky tu")
    return value


def save_trial(path, rows, user_id, session_id, trial_id, label, columns=COLUMNS, quality_check=timing_report):
    """Validate the complete trial before one append; never modify old datasets."""
    sensor_columns = tuple(k for k in columns if k not in ("user_id", "session_id", "trial_id", "label"))
    label = valid_label(label)
    quality = quality_check(rows)
    records = []
    for row in rows:
        if any(k not in row or not math.isfinite(float(row[k])) for k in sensor_columns):
            raise ValueError("Thieu/loi cot cam bien hoac IMU; khong luu trial")
        if any(not 0 <= float(row[k]) <= 4095 for k in sensor_columns if k.startswith("flex_")):
            raise ValueError("Flex ADC ngoai 0..4095; khong luu trial")
        if abs(sum(float(row[k])**2 for k in Q_COLUMNS)-1) > .001:
            raise ValueError("Quaternion khong hop le; khong luu trial")
        records.append({
            **{k: row[k] for k in sensor_columns},
            "timestamp": int(row["timestamp"]), "user_id": user_id,
            "session_id": session_id, "trial_id": trial_id, "label": label,
        })
    path = Path(path)
    exists = path.exists()
    if exists:
        with path.open("r", newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != list(columns):
                raise ValueError("File dich co header khac; khong ghi de")
            if any(row["session_id"] != session_id or int(row["trial_id"]) >= trial_id for row in reader):
                raise ValueError("Trung session/trial; khong ghi de")
    with path.open("a", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerows(records)
    return quality


def countdown():
    for number in (3, 2, 1):
        print(number, flush=True)
        time.sleep(1)


def build_parser(v2=False, five=False):
    parser = argparse.ArgumentParser(description="Collect five flex sensors + MPU in five-second trials." if five else __doc__)
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--label", default="NGHIENG_GAP_DUOI", type=valid_label)
    parser.add_argument("--seconds", type=float, default=5 if v2 else 3)
    parser.add_argument("--output-dir", type=Path, default=BASE / ("sequence_data_5" if five else "sequence_data_v2" if v2 else "sequence_data"))
    parser.add_argument("--demo-plan", action="store_true", default=v2 and not five, help="Alternate positives and six kinds of NONE")
    parser.add_argument("--manual-labels", action="store_false", dest="demo_plan")
    parser.add_argument("--rounds", type=int, default=2, help="Each round: 6 positive and 6 NONE trials")
    parser.set_defaults(review_trials=v2, five=five)
    return parser


def main(argv=None, v2=False, five=False):
    if five:
        if __package__:
            from .collect_sequence_5 import main as collect_five
        else:
            from collect_sequence_5 import main as collect_five
        return collect_five(argv)
    args = build_parser(v2, five).parse_args(argv)
    if five and args.demo_plan:
        print("LOI: --demo-plan chi danh cho demo 2 ngon; ban 5 ngon dung nhan tu chon va NONE")
        return 1
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", args.user_id):
        print("LOI: user-id chi dung A-Z, a-z, 0-9, _ hoac -")
        return 1
    if not 1.5 <= args.seconds <= 5:
        print("LOI: --seconds can trong 1.5..5.0 giay")
        return 1
    if (v2 or args.demo_plan) and args.seconds != 5:
        print("LOI: Quy trinh moi can tron 5 giay; khong tron voi du lieu 3 giay")
        return 1
    if args.rounds < 1 or (args.demo_plan and args.label == "NONE"):
        print("LOI: rounds >= 1 va nhan duong phai khac NONE")
        return 1
    args.plan_index = 0
    while True:
        try:
            return collect_session(args)
        except SamplingGap as error:
            print(f"\nTAM DUNG: {error}.")
            print("Lan thu chua hoan tat KHONG duoc luu. Cac trial DA LUU van con.")
            print("Se ket noi lai va tao phien moi de lay lai moc MPU.")
            try:
                while True:
                    command = input("ENTER: thu lai voi phien moi | Q: dung > ").strip().upper()
                    if command == "Q":
                        return 0
                    if not command:
                        break
                    print("Chi dung ENTER hoac Q")
            except (KeyboardInterrupt, EOFError):
                return 0


def collect_session(args):
    five = getattr(args, "five", False)
    columns = COLUMNS
    if five:
        if __package__:
            from .five_finger import CSV_COLUMNS, FLEX_PINS, FINGERS
        else:
            from five_finger import CSV_COLUMNS, FLEX_PINS, FINGERS
        columns = CSV_COLUMNS
    # Reconnect on recovery so no buffered packets or changed world origin can
    # leak into a new session. Completed CSV files are never reopened here.
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    folder = args.output_dir / session_id
    path = folder / "samples.csv"
    stream = None
    try:
        folder.mkdir(parents=True, exist_ok=False)
        sock = socket.create_connection((args.esp32_host, args.esp32_port), timeout=3)
        stream = SampleStream(sock, flex_count=5) if five else SampleStream(sock)
        print("DANG KIEM TRA DU LIEU ESP32... Giu tay nghi.", flush=True)
        ready = stream.check_ready()
        print(f"{'RAW5' if five else 'RAW2'} hop le, {ready['hz']:.2f} Hz", flush=True)
        input("Dat tay yen tren ban. Nhan Enter de lay moc MPU mot lan dau phien > ")
        countdown()
        print("GIU YEN khoang 4 giay: dang lay moc va khoi tao huong MPU...", flush=True)
        reference = make_imu_reference(stream.capture(2))
        stream.configure_imu(reference)
        stream.capture(2.1)
        if not stream.processor.ready:
            raise ValueError("MPU chua khoi tao xong; chay lai va giu yen tay")
        reference.update(user_id=args.user_id, session_id=session_id,
                         trial_seconds=args.seconds, csv_columns=list(columns))
        reference["collection_protocol"] = "mixed-two-flex-5s-v2" if getattr(args, "demo_plan", False) else "manual"
        if five:
            reference.update(flex_pins=FLEX_PINS, fingers=FINGERS,
                             collection_protocol="manual-five-flex-5s-v1")
        (folder / "imu_reference.json").write_text(json.dumps(reference, indent=2), encoding="utf-8")
        print(f"SAN SANG: luu {5 if five else 2} flex + quaternion + GYR + ACC + ACC_body + ACC_world.")
        if five:
            print("GPIO: cai=32, tro=33, giua=34, ap ut=35, ut=36.")
            print("Moi trial: 0.5s dau duoi tay/giu yen, sau do lam cu chi. Thu ca nhan NONE trong moi phien.")
            print("Dung C de doi nhan; thu it nhat 2 phien co du cac nhan, khuyen nghi 3 phien.")
        print("Flex luu ADC goc; khong yeu cau hieu chuan gap/duoi.")
        print("Khong sua dataset_gesture.csv, dataset_sentence.csv hay model cu.")
        print(f"File moi: {path}")
        print("Moi trial chua TRON chuoi dong tac, gan chung MOT nhan.")
        label = args.label
        trial_id = 1
        while True:
            planned = getattr(args, "demo_plan", False)
            subtype, instruction = "MANUAL", ""
            if planned:
                if args.plan_index >= args.rounds*12:
                    print(f"DA XONG: {args.rounds*6} mau dung + {args.rounds*6} NONE. Phien sau deo lai gang va thu du ca hai nhan.")
                    return 0
                label, subtype, instruction = demo_step(args.plan_index, args.label)
                print(f"\nMAU {args.plan_index+1}/{args.rounds*12}: {subtype} -> nhan {label}")
                print(instruction)
                print("0.5s DAU: hai ngon duoi/co tay yen. CUOI: duoi va giu yen de ghi do hoi cham.")
            command = input(f"\n[{label}] ENTER: thu {args.seconds:.1f}s | C: doi nhan | Q: dung > ").strip().upper()
            if command == "Q":
                return 0
            if command == "C":
                if planned:
                    print("Lich nay tu doi nhan dung/NONE. Dung --manual-labels neu can nhan moi.")
                    continue
                try:
                    label = valid_label(input("Nhap nhan moi, vi du TAM_BIET > "))
                except ValueError as error:
                    print("LOI:", error)
                continue
            if command:
                print("Chi dung ENTER, C hoac Q")
                continue
            stream.check_ready()
            countdown()
            stream.sock.sendall(b"START\n")
            print("BAT DAU: lam tron chuoi dong tac mot lan", flush=True)
            try:
                rows = stream.capture(args.seconds)
            finally:
                stream.sock.sendall(b"STOP\n")
            if getattr(args, "review_trials", False):
                while True:
                    review = input("Lam DUNG loi nhac? ENTER: luu | R: bo lan nay/thu lai | Q: bo va dung > ").strip().upper()
                    if review in ("", "R", "Q"):
                        break
                if review == "Q":
                    return 0
                if review == "R":
                    print("DA BO lan nay; cac trial truoc giu nguyen.")
                    continue
            quality = save_trial(path, rows, args.user_id, session_id, trial_id, label, columns=columns)
            print(f"DA LUU trial {trial_id}: {quality['samples']} mau, "
                  f"{quality['hz']:.2f} Hz, gap max {quality['max_gap_ms']:.0f} ms")
            if planned:
                args.plan_index += 1
                # The CSV is authoritative; notes only document the requested
                # subtype, not an automatic verification of the user's action.
                try:
                    with (folder/"trial_notes.jsonl").open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"trial_id": trial_id, "label": label,
                                            "subtype": subtype, "instruction": instruction})+"\n")
                except OSError as error:
                    print(f"LUU Y: CSV DA LUU, nhung khong ghi duoc ghi chu: {error}")
            trial_id += 1
    except SamplingGap:
        print(f"Phien vua dung: {folder}")
        raise
    except (OSError, ValueError) as error:
        print(f"LOI: {error}. Trial dang thu khong duoc luu; trial truoc van con.")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nDa dung; trial chua hoan tat khong duoc luu.")
        return 0
    finally:
        if stream:
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
