"""Five-finger sliding-window recognition over Wi-Fi; no per-gesture Enter."""
import argparse
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import re
import socket
import time

if __package__:
    from .collect_v2 import SampleStream
    from .serial_transport import SerialTransport
    from .collect_sequence_5 import calibrate
    from .five_finger import validate_reference, trial_quality
    from .sensor_pipeline import make_imu_reference
    from .sequence_model_5 import SequenceModel, MODEL_PREFIX, DATA_DIRECTORY
else:
    from collect_v2 import SampleStream
    from serial_transport import SerialTransport
    from collect_sequence_5 import calibrate
    from five_finger import validate_reference, trial_quality
    from sensor_pipeline import make_imu_reference
    from sequence_model_5 import SequenceModel, MODEL_PREFIX, DATA_DIRECTORY

BASE = Path(__file__).resolve().parent


class SlidingRecognizer:
    """Use 150 actual samples and the training preprocessor; never bridge a gap."""
    def __init__(self, model, reference, step_ms=250, confirmations=2):
        self.model = model
        self.reference = reference
        self.step_ms = step_ms
        self.confirmations = confirmations
        self.window = deque(maxlen=150)
        self.last_stamp = None
        self.last_prediction = None
        self.candidate = None
        self.streak = 0

    def clear(self):
        self.window.clear()
        self.last_prediction = None
        self.candidate = None
        self.streak = 0

    def update(self, batch):
        interrupted = False
        for row in batch:
            stamp = row["timestamp"]
            if self.last_stamp is not None:
                if stamp <= self.last_stamp:
                    self.clear()
                    raise ValueError("Timestamp quay nguoc; khoi tao lai ket noi")
                if stamp - self.last_stamp > 20:
                    self.clear()
                    interrupted = True
            self.last_stamp = stamp
            self.window.append(row)
        if not batch:
            return None
        if len(self.window) < 150:
            return {"state": "WAIT", "reason": "Bo cua so bi gian doan; cho du 150 mau moi"} if interrupted else None
        if self.last_prediction is not None and self.last_stamp - self.last_prediction < self.step_ms:
            return None
        self.last_prediction = self.last_stamp
        rows = list(self.window)
        try:
            quality = trial_quality(rows)
        except ValueError as error:
            self.clear()
            return {"state": "ERROR", "reason": str(error)}
        candidate = self.model.predict(rows, self.reference)
        self.streak = self.streak + 1 if candidate == self.candidate else 1
        self.candidate = candidate
        if self.streak < self.confirmations:
            return {"state": "WAIT", "candidate": candidate, "reason": "Dang xac nhan ky hieu moi"}
        return {"state": "RESULT", "label": candidate, "hz": quality["hz"], "timestamp": self.last_stamp}


def send_state(sock, state):
    if state not in {"WAIT", "ERROR", "OFF"}:
        raise ValueError("Invalid live state")
    sock.sendall(f"LIVE_STATE,{state}\n".encode("ascii"))


def send_result(sock, label):
    if not re.fullmatch(r"[A-Z0-9_]{1,48}", label):
        raise ValueError("Invalid live label")
    # SVC was trained without calibrated probabilities: do not invent a percent.
    sock.sendall(f"LIVE,{label}\n".encode("ascii"))


def initialize_imu(stream, saved_reference):
    stream.sock.sendall(b"RUN,CALIBRATING\n")
    print("GIU TAY YEN khoang 5 giay de lay moc MPU. Khong can nhan Enter.", flush=True)
    while True:
        try:
            raw = stream.capture(3)
            boundary = raw[-1]["timestamp"] - 2000
            measured = make_imu_reference([r for r in raw if r["timestamp"] >= boundary], sample_ms=10)
            break
        except ValueError as error:
            if stream.error:
                raise stream.error
            print(f"CHUA ON DINH: {error}. Giu yen, chuong trinh tu do lai.", flush=True)
    reference = deepcopy(saved_reference)
    reference.update(measured)
    reference["flex_calibrated"] = True
    validate_reference(reference)
    stream.configure_imu(reference)
    stream.capture(2.1)
    if not stream.processor.ready:
        raise ValueError("MPU chua san sang")
    return reference


def recognize(stream, model, reference):
    detector = SlidingRecognizer(model, reference)
    # Start after warmup. No pre-initialization/backlogged samples enter a window.
    with stream.condition:
        cursor = stream.serial
    send_state(stream.sock, "WAIT")
    print("SAN SANG: tao A/B/C/D hoac tha long (NONE); giu moi ky hieu khoang 2 giay.", flush=True)
    print("Tu cap nhat moi 0.25 giay tren cua so 1.5 giay. Ctrl+C de dung.", flush=True)
    last_data = time.monotonic()
    stalled = False
    while True:
        cursor, batch = stream.read_since(cursor, timeout=.25)
        if not batch:
            if time.monotonic() - last_data > .5 and not stalled:
                detector.clear()
                send_state(stream.sock, "WAIT")
                print("CHO: du lieu cham; bo cua so cu, cho mau moi (chua ngat ket noi).", flush=True)
                stalled = True
            if time.monotonic() - last_data > 3:
                raise ValueError("Khong co mau moi trong 3 giay; ket noi lai")
            continue
        last_data = time.monotonic()
        if stalled:
            # Discard the first resumed batch: it may be a transport backlog.
            stalled = False
            continue
        event = detector.update(batch)
        if event is None:
            continue
        if event["state"] == "RESULT":
            send_result(stream.sock, event["label"])
            text = "NONE (khong phai ky hieu da hoc)" if event["label"] == "NONE" else event["label"]
            print(f"KET QUA: {text} | {event['hz']:.2f} Hz", flush=True)
        else:
            send_state(stream.sock, event["state"])
            print(f"CHO: {event['reason']}", flush=True)


def latest_model():
    folders = [p.parent for p in (BASE/"models").glob(MODEL_PREFIX+"*/manifest.json")
               if (p.parent/"model.joblib").exists() and (p.parent/"report.json").exists()]
    if not folders:
        raise ValueError("Chua co model 5 ngon; chay train_sequence_5.py truoc")
    return max(folders, key=lambda p: (p/"manifest.json").stat().st_mtime_ns)


def latest_reference():
    paths = [p.parent/"imu_reference.json" for p in (BASE/DATA_DIRECTORY).rglob("*.csv")
             if p.stat().st_size > 0 and (p.parent/"imu_reference.json").exists()]
    if not paths:
        raise ValueError("Chua co moc flex; them --recalibrate de hieu chuan lan dau")
    return max(paths, key=lambda p: p.stat().st_mtime_ns)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    parser.add_argument("--serial-port", help="Recognize over USB, e.g. COM3, at 230400 baud")
    parser.add_argument("--model", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reference", type=Path, help="Existing five-flex calibration JSON")
    group.add_argument("--recalibrate", action="store_true", help="Calibrate all five fingers together before continuous recognition")
    args = parser.parse_args(argv)
    try:
        folder = args.model or latest_model()
        model = SequenceModel(folder)
        saved_reference = None
        print(f"MODEL 5 NGON: {folder}")
        print("NHAN: " + ", ".join(model.manifest["labels"]))
        if "NONE" not in model.manifest["labels"]:
            print("THU NGHIEM KHONG NONE: model van chon ky hieu khi nghi tay; khong co kha nang tu choi dong tac la.")
        if model.manifest.get("evaluation_scope") == "full_data_no_test":
            print("Model train toan bo du lieu, khong co ket qua test rieng.")
        elif model.manifest.get("evaluation_scope") != "session_holdout":
            print("Model moi danh gia trong cung phien; do chinh xac live can kiem tra tren gang that.")
        if not args.recalibrate:
            path = args.reference or latest_reference()
            saved_reference = validate_reference(json.loads(path.read_text(encoding="utf-8")))
            print(f"MOC FLEX: {path}")
            print("Neu da thao/deo hoac chinh cam bien: dung Ctrl+C, chay lai voi --recalibrate.")
    except (OSError, ValueError, KeyError) as error:
        print(f"LOI CAU HINH: {error}")
        return 1
    try:
        while True:
            stream = None
            sock = None
            try:
                if args.serial_port:
                    print(f"Ket noi USB {args.serial_port}, 230400 baud...", flush=True)
                    sock = SerialTransport(args.serial_port)
                else:
                    print(f"Ket noi Wi-Fi {args.esp32_host}:{args.esp32_port}...", flush=True)
                    sock = socket.create_connection((args.esp32_host, args.esp32_port), timeout=3)
                stream = SampleStream(sock, flex_count=5, sample_ms=10)
                if saved_reference is None:
                    saved_reference = calibrate(stream)
                    if saved_reference is None:
                        return 0
                    reference = saved_reference
                else:
                    reference = initialize_imu(stream, saved_reference)
                recognize(stream, model, reference)
            except (OSError, ValueError) as error:
                print(f"TAM DUNG: {error}. Tu noi lai; giu tay yen de khoi tao MPU.", flush=True)
                if sock:
                    try:
                        send_state(sock, "ERROR")
                    except OSError:
                        pass
            finally:
                if stream:
                    try:
                        send_state(stream.sock, "OFF")
                    except OSError:
                        pass
                    stream.close()
                elif sock:
                    sock.close()
            time.sleep(2)
    except (KeyboardInterrupt, EOFError):
        print("\nDa dung nhan dien lien tuc.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
