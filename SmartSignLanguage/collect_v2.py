"""Fixed-duration raw + derived IMU collection; independent, calibrated sessions.

Run --help. Requires the RAW2-capable firmware. No model is needed for collection.
"""
import argparse
from collections import deque
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import threading
import time
import uuid

if __package__:
    from .sensor_pipeline import (CSV_COLUMNS, LABELS, SensorProcessor, ImuProcessor, from_legacy,
                                  make_calibration, timing_report, SamplingGap)
    from .wifi_ai import parse_sensor_line
    from .five_finger import parse_raw5, raw5_error_detail
else:
    from sensor_pipeline import (CSV_COLUMNS, LABELS, SensorProcessor, ImuProcessor, from_legacy,
                                 make_calibration, timing_report, SamplingGap)
    from wifi_ai import parse_sensor_line
    from five_finger import parse_raw5, raw5_error_detail

BASE = Path(__file__).resolve().parent


class SampleStream:
    """Drain the transport during prompts/countdowns; never train on a backlog."""
    def __init__(self, sock, flex_count=2, sample_ms=40, recover_collection_gaps=False):
        if flex_count not in (2, 5):
            raise ValueError("Expected 2 or 5 flex channels")
        self.flex_count = flex_count
        if sample_ms not in (10, 40) or (sample_ms == 10 and flex_count != 5):
            raise ValueError("100 Hz requires five-channel firmware")
        self.sample_ms = sample_ms
        self.protocol = "RAW5_100" if sample_ms == 10 else "RAW5" if flex_count == 5 else "RAW2"
        self.sock = sock
        sock.settimeout(.25)
        self.condition = threading.Condition()
        self.rows = deque(maxlen=2000 if sample_ms == 10 else 500)
        self.processor = None
        self.error = None
        self.recover_collection_gaps = recover_collection_gaps
        self.recovery_required = None
        self.bad_packet_times = deque()
        self.closed = threading.Event()
        self.last_stamp = None
        self.serial = 0
        self.begin_serial = None
        sock.sendall((self.protocol + "\n").encode("ascii"))
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        pending = b""
        last = time.monotonic()
        try:
            while not self.closed.is_set():
                # Traffic in another format must not keep an unusable stream alive.
                if time.monotonic()-last > 3:
                    raise ValueError(f"Khong co {self.protocol} hop le trong 3 giay. Kiem tra firmware/ket noi ESP32.")
                try:
                    chunk = self.sock.recv(4096)
                except socket.timeout:
                    if time.monotonic()-last > 3:
                        raise ValueError(f"Khong co {self.protocol} moi. Nap firmware moi va kiem tra ket noi.")
                    continue
                if not chunk:
                    raise ValueError("ESP32 ngat ket noi; phien thu da dung")
                pending += chunk
                if len(pending) > 65536:
                    raise ValueError("Sensor line too long")
                while b"\n" in pending:
                    line, pending = pending.split(b"\n",1)
                    if line.strip() == b"BEGIN":
                        with self.condition:
                            if self.begin_serial == -1:
                                self.begin_serial = self.serial
                                self.condition.notify_all()
                        continue
                    if not line.startswith((self.protocol + ",").encode("ascii")):
                        if line.startswith((b"DATA,", b"DATA5,", b"RAW2,")) and time.monotonic()-last > 1:
                            if self.flex_count == 2 and line.startswith(b"DATA,"):
                                raise ValueError("ESP32 dang gui DATA cu, chua gui RAW2. Nap lai mophong_wireless.ino hien tai roi chay lai.")
                            raise ValueError(f"ESP32 chua gui {self.protocol}. Nap lai mophong_wireless.ino hien tai roi chay lai.")
                        continue
                    if self.flex_count == 5:
                        sample = parse_raw5(line, protocol=self.protocol)
                    else:
                        sample = parse_sensor_line(line)
                    if sample is None:
                        detail = raw5_error_detail(line) if self.flex_count == 5 else repr(line[:220])
                        error = ValueError(f"Goi {self.protocol} sai dinh dang: {detail}")
                        now = time.monotonic()
                        self.bad_packet_times.append(now)
                        while self.bad_packet_times and now-self.bad_packet_times[0] > 10:
                            self.bad_packet_times.popleft()
                        if len(self.bad_packet_times) >= 3:
                            raise ValueError(f"3 goi hong trong 10 giay; dung de kiem tra cap USB/cong COM. {error}")
                        with self.condition:
                            if not self.recover_collection_gaps or (self.processor is None and self.recovery_required is None):
                                raise error
                            # Discard the entire damaged line, even if it contains
                            # another packet prefix. Never splice corrupted bytes
                            # into a training window or integrate across the loss.
                            self.recovery_required = error
                            self.processor = None
                            self.rows.clear()
                            self.condition.notify_all()
                        continue
                    stamp, values = sample
                    with self.condition:
                        if self.last_stamp is not None and stamp <= self.last_stamp:
                            raise ValueError("ESP32 reset/timestamp quay nguoc; tao phien thu moi")
                        self.last_stamp = stamp
                        raw = values if self.flex_count == 5 else from_legacy(values)
                        row = {"timestamp": stamp, **raw}
                        if self.processor:
                            try:
                                row.update(self.processor.process(stamp, raw))
                            except SamplingGap as exc:
                                if not self.recover_collection_gaps:
                                    raise
                                # Keep draining raw packets, but prohibit capture
                                # until the wearer explicitly reinitializes IMU.
                                self.recovery_required = exc
                                self.processor = None
                                self.rows.clear()
                        self.serial += 1
                        self.rows.append((self.serial,row))
                        self.condition.notify_all()
                    last = time.monotonic()
        except (OSError, ValueError) as exc:
            if not self.closed.is_set():
                with self.condition:
                    self.error = exc
                    self.condition.notify_all()

    def configure(self, calibration):
        with self.condition:
            self.processor = SensorProcessor(calibration)
            self.rows.clear()

    def check_ready(self):
        """Check fresh samples and timing before asking the wearer to perform."""
        return self.quality_check(self.capture(.4))

    def quality_check(self, rows):
        return timing_report(rows, self.sample_ms, 20 if self.sample_ms == 10 else 120)

    def configure_imu(self, reference):
        with self.condition:
            self.processor = ImuProcessor(reference)
            self.recovery_required = None
            self.rows.clear()

    def enable_runtime_recovery(self):
        """Opt-in only after initial warmup; return the matching stream cursor."""
        if __package__:
            from .runtime_imu import RuntimeImuProcessor
        else:
            from runtime_imu import RuntimeImuProcessor
        with self.condition:
            if self.error:
                raise self.error
            if not isinstance(self.processor, ImuProcessor) or not self.processor.ready:
                raise ValueError("Initialize IMU before enabling runtime recovery")
            self.processor = RuntimeImuProcessor(self.processor)
            self.rows.clear()
            return self.serial

    def start_trial(self):
        """Bind capture to firmware BEGIN, excluding pre-countdown/backlog data."""
        with self.condition:
            if self.error:
                raise self.error
            if self.recovery_required:
                raise self.recovery_required
            self.begin_serial = -1
            self.sock.sendall(b"START\n")
            self.condition.wait_for(lambda: self.error or self.recovery_required or self.closed.is_set() or self.begin_serial != -1, 3)
            if self.error:
                raise self.error
            if self.recovery_required:
                raise self.recovery_required
            if self.begin_serial == -1 or self.closed.is_set():
                raise ValueError("Khong nhan BEGIN; khong thu trial")
            return self.begin_serial

    def capture(self, seconds, sample_count=None, after=None):
        deadline = time.monotonic()+seconds+4
        with self.condition:
            if self.processor is not None and not isinstance(self.processor, ImuProcessor):
                raise ValueError("Runtime recovery stream cannot collect training windows; use read_since")
            after = self.serial if after is None else after
            while True:
                if self.error:
                    raise self.error
                if self.recovery_required:
                    raise self.recovery_required
                batch = [(n, r) for n, r in self.rows if n > after]
                if batch and batch[0][0] != after+1:
                    raise ValueError("Mat mau trong bo dem; thu lai trial")
                rows = [r.copy() for _,r in batch]
                if sample_count is not None:
                    if len(rows) >= sample_count:
                        result = rows[:sample_count]
                        self.quality_check(result)
                        return result
                elif len(rows)>1 and rows[-1]["timestamp"]-rows[0]["timestamp"] >= seconds*1000:
                    self.quality_check(rows)
                    return rows
                left = deadline-time.monotonic()
                if left<=0:
                    raise ValueError("Thieu mau/thoi gian thu qua han; khong luu trial")
                self.condition.wait(min(.25,left))

    def close(self):
        self.closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        self.thread.join(1)

    def read_since(self, cursor, timeout=1.0):
        """Consume each sample once; fail rather than silently skip a backlog."""
        with self.condition:
            self.condition.wait_for(lambda: self.error or self.closed.is_set() or self.serial > cursor, timeout)
            if self.error:
                raise self.error
            if self.closed.is_set():
                raise OSError("Stream closed")
            batch = [(n, r.copy()) for n, r in self.rows if n > cursor]
            if batch and batch[0][0] != cursor+1:
                raise ValueError("Mat mau trong hang doi; khoi tao lai nhan dien")
            if batch and batch[-1][1]["timestamp"]-batch[0][1]["timestamp"] > 1000:
                raise ValueError("Xu ly cham hon luong cam bien; bo hang doi cu va ket noi lai")
            return (batch[-1][0] if batch else cursor), [r for _, r in batch]


def countdown():
    for n in (3,2,1):
        print(n, flush=True)
        time.sleep(1)


def record_pose(stream, instruction):
    input(instruction+" Nhan Enter khi da san sang > ")
    countdown()
    print("GIU YEN (2 giay)...", flush=True)
    return stream.capture(2)


def calibrate(stream, finger):
    opened = record_pose(stream,"Duoi hai ngon co cam bien; cho flex on dinh.")
    closed = record_pose(stream,"Gap hai ngon co cam bien; giu on dinh.")
    rest = record_pose(stream,"Duoi lai hai ngon; giu yen ca ban tay de do gyro bias.")
    result = make_calibration(opened,closed,rest,finger)
    # Return-to-open check catches slow recovery before it poisons subsequent trials.
    for key in ("flex_1","flex_2"):
        import numpy as np
        median = float(np.median([r[key] for r in rest]))
        span = abs(result[key]["closed"]-result[key]["open"])
        if abs(median-result[key]["open"]) > max(15,.15*span):
            raise ValueError(f"{key} chua hoi ve moc duoi. Kiem tra cach gan/cam bien, cho on dinh roi thu lai.")
    return result


def save_trial(path, rows, metadata, trial_id, label):
    if label not in LABELS:
        raise ValueError("Nhan chua duoc web ho tro")
    quality = timing_report(rows)
    if not 2200 <= quality["duration_ms"] <= 2700:
        raise ValueError("Trial must span about 2.4 seconds; no arbitrary time warping")
    records = [{**r,"user_id":metadata["user_id"],"session_id":metadata["session_id"],
                "trial_id":trial_id,"label":label} for r in rows]
    # Validate the whole batch before appending anything.
    import math
    for r in records:
        if not all(k in r for k in CSV_COLUMNS) or not all(math.isfinite(float(r[k])) for k in CSV_COLUMNS if k not in ("user_id","session_id","label")):
            raise ValueError("Incomplete/nonfinite row; trial not saved")
    path = Path(path)
    if path.exists():
        with path.open(encoding="utf-8",newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != list(CSV_COLUMNS):
                raise ValueError("CSV schema mismatch; keeping existing file")
            existing = list(reader)
            if any(r["session_id"] != metadata["session_id"] or r["user_id"] != metadata["user_id"] or int(r["trial_id"]) >= trial_id for r in existing):
                raise ValueError("Session/trial identity conflict; keeping existing file")
    new = not path.exists()
    with path.open("a",encoding="utf-8",newline="") as out:
        writer = csv.DictWriter(out,fieldnames=CSV_COLUMNS,extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerows(records)
    return quality


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--esp32-host",default="192.168.137.115")
    p.add_argument("--esp32-port",type=int,default=5000)
    p.add_argument("--user-id",required=True)
    p.add_argument("--flex1-finger",choices=("Index","Middle"),default="Index")
    p.add_argument("--output-dir",type=Path,default=BASE/"data_v2")
    p.add_argument("--calibration-output",type=Path,default=BASE/"calibration"/"current.json")
    p.add_argument("--calibrate-only",action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}",args.user_id):
        raise SystemExit("user-id: dung 1-40 ky tu A-Z, a-z, 0-9, _ hoac -")
    stream = None
    try:
        print("Dung wifi_ai.py truoc. Giu nguyen vi tri flex/IMU trong ca phien.")
        stream = SampleStream(socket.create_connection((args.esp32_host,args.esp32_port),timeout=3))
        calibration = calibrate(stream,args.flex1_finger)
        session = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
        calibration.update(user_id=args.user_id,session_id=session,created_utc=datetime.now(timezone.utc).isoformat())
        folder = args.output_dir/session
        folder.mkdir(parents=True,exist_ok=False)
        content = json.dumps(calibration,indent=2,ensure_ascii=False)+"\n"
        (folder/"calibration.json").write_text(content,encoding="utf-8")
        args.calibration_output.parent.mkdir(parents=True,exist_ok=True)
        args.calibration_output.write_text(content,encoding="utf-8")
        print(f"Da luu moc: {args.calibration_output}\nPhien: {folder}")
        if args.calibrate_only:
            return 0
        stream.configure(calibration)
        print("Giu yen tay 2.4 giay de khoi tao IMU...")
        stream.capture(2.4)
        label = "XIN_CHAO"
        trial = 1
        while True:
            cmd = input(f"[{label}] Enter: thu 2.4s | 1: Xin chao | 2: Cam on nhieu | 3: NONE | Q: dung > ").strip().upper()
            if cmd=="Q":
                return 0
            if cmd in ("1","2","3"):
                label = LABELS[int(cmd)-1]
                continue
            if cmd:
                continue
            countdown()
            stream.sock.sendall(b"START\n")
            print("BAT DAU: thuc hien dung mot luot cu chi.",flush=True)
            try:
                rows = stream.capture(2.4)
            finally:
                stream.sock.sendall(b"STOP\n")
            quality = save_trial(folder/"samples.csv",rows,calibration,trial,label)
            print(f"DA LUU trial {trial}: {quality['samples']} mau, {quality['hz']:.2f} Hz, gap max {quality['max_gap_ms']:.0f} ms")
            trial += 1
    except (OSError,ValueError,KeyError) as exc:
        print(f"LOI: {exc}. Khong luu trial dang thu; cac trial truoc van duoc giu.")
        return 1
    except (KeyboardInterrupt,EOFError):
        print("Da dung; khong luu trial chua hoan tat.")
        return 0
    finally:
        if stream:
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
