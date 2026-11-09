"""Collect complete BEGIN/DATA/END trials without blocking the ESP32 stream."""

import argparse
import csv
from pathlib import Path
import re
import socket
import threading
import time

if __package__:
    from .wifi_ai import FEATURE_NAMES, parse_sensor_line
else:
    from wifi_ai import FEATURE_NAMES, parse_sensor_line


CSV_FILE = Path(__file__).resolve().parent / "dataset_sentence.csv"
COLUMNS = ["trial_id", "label", "time_ms", *FEATURE_NAMES]


class CollectorError(RuntimeError):
    """A trial could not be completed safely and must not be saved."""


class TrialRecorder:
    """One reader owns the TCP stream, including while the CLI waits for input."""

    def __init__(self, sock, timeout=5.0):
        self.sock = sock
        self.timeout = timeout
        self.sock.settimeout(0.25)
        self._lock = threading.Lock()
        self._started = threading.Event()
        self._ended = threading.Event()
        self._closed = threading.Event()
        self._state = "idle"
        self._connected = True
        self._error = None
        self._samples = []
        self._first_stamp = None
        self._last_stamp = None
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _fail_locked(self, message):
        self._error = message
        self._state = "failed"
        self._started.set()
        self._ended.set()

    def _check_locked(self):
        if self._error:
            raise CollectorError(self._error)
        if not self._connected:
            raise CollectorError("ESP32 da ngat ket noi.")

    def _send(self, command):
        try:
            self.sock.sendall(command)
        except OSError as exc:
            with self._lock:
                self._fail_locked("Khong gui duoc lenh den ESP32.")
            raise CollectorError(self._error) from exc

    def _wait(self, event, marker):
        if not event.wait(self.timeout):
            with self._lock:
                self._fail_locked(f"Qua thoi gian cho {marker}; trial khong duoc luu.")
        with self._lock:
            self._check_locked()

    def start_trial(self):
        with self._lock:
            self._check_locked()
            if self._state not in ("idle", "complete"):
                raise CollectorError("Trial truoc chua ket thuc.")
            self._samples = []
            self._first_stamp = self._last_stamp = None
            self._started.clear()
            self._ended.clear()
            self._state = "starting"
        self._send(b"START\n")
        self._wait(self._started, "BEGIN")

    def stop_trial(self):
        with self._lock:
            self._check_locked()
            if self._state != "recording":
                raise CollectorError("Khong co trial dang thu.")
            self._state = "stopping"
        self._send(b"STOP\n")
        self._wait(self._ended, "END")
        with self._lock:
            if self._state != "complete" or not self._samples:
                raise CollectorError("Trial rong hoac khong hoan chinh; khong luu.")
            return tuple(self._samples)

    def _consume(self, line):
        with self._lock:
            if self._state not in ("starting", "recording", "stopping"):
                return
            if line == b"BEGIN":
                if self._state != "starting":
                    self._fail_locked("BEGIN trung lap; trial khong hoan chinh.")
                else:
                    self._state = "recording"
                    self._started.set()
                return
            if line == b"END":
                if self._state != "stopping":
                    self._fail_locked("Nhan END truoc khi gui STOP.")
                else:
                    self._state = "complete"
                    self._ended.set()
                return
            if self._state == "starting":
                return  # Previously queued DATA before BEGIN is outside this trial.
            sample = parse_sensor_line(line)
            if sample is None:
                self._fail_locked("Du lieu cam bien sai dinh dang/khong huu han; khong luu.")
                return
            stamp, features = sample
            if self._last_stamp is not None and (stamp <= self._last_stamp or stamp - self._last_stamp > 250):
                self._fail_locked("ESP32 reset hoac mat nhip cam bien; khong luu.")
                return
            if self._first_stamp is None:
                self._first_stamp = stamp
            self._last_stamp = stamp
            self._samples.append((stamp - self._first_stamp, *features))
            if len(self._samples) > 15000:
                self._fail_locked("Trial qua dai (>15000 mau); chia thanh nhieu trial ngan.")

    def _read(self):
        line = bytearray()
        oversized = False
        last_receive = time.monotonic()
        try:
            while not self._closed.is_set():
                try:
                    chunk = self.sock.recv(4096)
                except socket.timeout:
                    if time.monotonic() - last_receive > self.timeout:
                        raise TimeoutError("ESP32 khong gui du lieu cam bien.")
                    continue
                if not chunk:
                    raise ConnectionError("ESP32 da ngat ket noi.")
                last_receive = time.monotonic()
                for value in chunk:
                    if value == 10:
                        if not oversized:
                            self._consume(bytes(line).rstrip(b"\r"))
                        line.clear()
                        oversized = False
                    elif not oversized:
                        if len(line) >= 2048:
                            oversized = True
                            with self._lock:
                                if self._state in ("recording", "stopping"):
                                    self._fail_locked("Dong du lieu qua dai; khong luu.")
                            line.clear()
                        else:
                            line.append(value)
        except OSError as exc:
            if not self._closed.is_set():
                with self._lock:
                    self._connected = False
                    self._fail_locked(f"Mat ket noi ESP32: {exc}")

    def close(self):
        self._closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        self._reader.join(timeout=1)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def valid_label(value):
    value = value.strip().upper().replace(" ", "_")
    if not re.fullmatch(r"[A-Z0-9_]{1,48}", value):
        raise ValueError("Nhan can 1-48 ky tu A-Z, 0-9 hoac dau gach duoi.")
    return value


def append_trial(output, label, samples):
    """Append only after stop_trial succeeds; never change earlier trials."""
    label = valid_label(label)
    if not samples:
        raise CollectorError("Trial rong; khong luu.")
    output = Path(output)
    has_header = output.exists() and output.stat().st_size > 0
    trial_id = 1
    if has_header:
        with output.open("r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != COLUMNS:
                raise CollectorError("Cot CSV khong khop; giu nguyen file hien co.")
            for row in reader:
                trial_id = max(trial_id, int(row["trial_id"]) + 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        if not has_header:
            writer.writerow(COLUMNS)
        writer.writerows((trial_id, label, *sample) for sample in samples)
    return trial_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    parser.add_argument("--output", type=Path, default=CSV_FILE)
    parser.add_argument("--label", default="XIN_CHAO", type=valid_label)
    args = parser.parse_args(argv)
    print("LEGACY collector: du lieu moi theo nghien cuu dung collect_v2.py; file nay khong cap nhat model v2.")
    label = args.label
    print("Dung wifi_ai.py truoc khi thu: ESP32 chi phuc vu mot TCP client.")
    print(f"Dataset: {args.output}")
    try:
        sock = socket.create_connection((args.esp32_host, args.esp32_port), timeout=5)
        with TrialRecorder(sock) as recorder:
            while True:
                command = input(f"\n[{label}] ENTER: thu | C: doi nhan | Q: thoat > ").strip().upper()
                if command == "Q":
                    return 0
                if command == "C":
                    try:
                        label = valid_label(input("Nhan moi > "))
                    except ValueError as exc:
                        print(exc)
                    continue
                if command:
                    print("Chi dung ENTER, C hoac Q.")
                    continue
                recorder.start_trial()
                input("DANG THU: thuc hien cu chi, ENTER khi xong > ")
                samples = recorder.stop_trial()
                if len(samples) < 5:
                    print("Trial qua ngan (<5 mau), khong luu.")
                    continue
                trial_id = append_trial(args.output, label, samples)
                print(f"Da luu trial {trial_id}: {len(samples)} mau, {samples[-1][0] / 1000:.2f} giay.")
    except (KeyboardInterrupt, EOFError):
        print("\nDa dung. Trial dang thu khong duoc luu.")
        return 0
    except (OSError, ValueError, CollectorError) as exc:
        print(f"\nLOI: {exc}\nTrial hien tai khong duoc luu. Kiem tra ket noi roi chay lai.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
