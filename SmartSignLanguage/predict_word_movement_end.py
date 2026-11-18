"""Continuously recognize U4 words and end a sentence after sustained rest."""
import argparse
from collections import Counter, deque
import json
from pathlib import Path
import time

import numpy as np

from .collect_sequence_5 import calibrate
from .collect_v2 import SampleStream
from .predict_continuous_5 import initialize_imu, latest_reference, send_result, send_state
from .five_finger import trial_quality, validate_reference
from .sequence_model_5 import FLEX_COLUMNS, FLEX_PINS, SequenceModel, legacy
from .serial_transport import SerialTransport


BASE = Path(__file__).resolve().parent
DEFAULT_MODEL = BASE / "models/sequence_5_100hz_U4_extra_trees_20261112"
FINGER_NAMES = ("CAI", "TRO", "GIUA", "AP UT", "UT")


def validate_flex_row(row):
    for key, pin, finger in zip(FLEX_COLUMNS, FLEX_PINS, FINGER_NAMES):
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            value = row.get(key, "khong doc duoc")
            raise ValueError(f"Flex loi: ngon {finger}, GPIO {pin} ({key}), ADC={value}")
        if not np.isfinite(value) or value <= 8 or value >= 4087:
            raise ValueError(
                f"Flex loi: ngon {finger}, GPIO {pin} ({key}), ADC={value:g}; "
                "kiem tra/day cam bien, ADC hop le la 9..4086"
            )


def pose(row, reference):
    flex = []
    for key in FLEX_COLUMNS:
        calibration = reference["flex_calibration"][key]
        flex.append((float(row[key]) - calibration["open"]) /
                    (calibration["closed"] - calibration["open"]))
    body = np.asarray([float(row[key]) for key in legacy.BODY_COLUMNS])
    raw_accel = np.asarray([float(row[key]) for key in ("ACCx", "ACCy", "ACCz")])
    gravity = (raw_accel - body) / reference["gravity"]
    raw_gyro = np.asarray([float(row[key]) for key in ("GYRx", "GYRy", "GYRz")])
    gyro = float(np.linalg.norm(raw_gyro - np.asarray(reference["gyro_bias"])))
    accel = float(np.linalg.norm(body))
    return np.asarray(flex), gravity, gyro, accel


def measure_rest(rows, reference):
    if len(rows) < 50:
        raise ValueError("Moc nghi can toi thieu 50 mau")
    for row in rows:
        validate_flex_row(row)
    samples = [pose(row, reference) for row in rows]
    gyro = np.asarray([sample[2] for sample in samples])
    if np.percentile(gyro, 95) > .5:
        raise ValueError("Tay con chuyen dong khi lay moc nghi")
    flex = np.stack([sample[0] for sample in samples])
    noise = np.percentile(flex, 95, axis=0) - np.percentile(flex, 5, axis=0)
    return {"flex": np.median(flex, axis=0), "noise": noise}


class MovementBoundary:
    """Segment signs by movement and stillness, without requiring flex reset."""

    def __init__(self, reference, rest, word_rest_ms=300):
        self.reference = reference
        self.rest = rest
        spans = np.asarray([
            abs(reference["flex_calibration"][key]["closed"] -
                reference["flex_calibration"][key]["open"])
            for key in FLEX_COLUMNS
        ])
        noise_adc = np.asarray(rest["noise"]) * spans
        self.start_flex_adc = np.maximum(10.0, noise_adc * 3.0)
        self.quiet_flex_adc = np.maximum(20.0, noise_adc * 2.0)
        self.word_rest_ms = word_rest_ms
        self.initial_flex_raw = np.asarray([
            reference["flex_calibration"][key]["open"] + rest["flex"][i] *
            (reference["flex_calibration"][key]["closed"] -
             reference["flex_calibration"][key]["open"])
            for i, key in enumerate(FLEX_COLUMNS)
        ])
        self.reset()

    def reset(self, wait_for_rest=False):
        self.state = "WAIT_REST" if wait_for_rest else "WAIT_START"
        self.recent = deque(maxlen=25)
        self.motion_history = deque(maxlen=200)
        self.baseline_raw = self.initial_flex_raw.copy()
        self.baseline_since = None
        self.onset_rows = []
        self.onset_since = None
        self.active_since = None
        self.rest_since = None
        self.last_stamp = None
        self.last_distance = None
        self.last_flex_range = None
        self.last_gyro = None
        self.last_accel = None
        self.last_at_rest = False

    def _raw_flex(self, row):
        return np.asarray([float(row[key]) for key in FLEX_COLUMNS])

    def _update_quiet_history(self, stamp, raw_flex, gyro):
        self.motion_history.append((stamp, raw_flex.copy(), gyro))
        recent = [item for item in self.motion_history if stamp - item[0] <= 120]
        if len(recent) < 6 or recent[-1][0] - recent[0][0] < 50:
            self.last_flex_range = None
            return False
        values = np.stack([item[1] for item in recent])
        flex_range = np.percentile(values, 95, axis=0) - np.percentile(values, 5, axis=0)
        gyro_p90 = float(np.percentile([item[2] for item in recent], 90))
        self.last_flex_range = flex_range
        self.last_gyro = gyro_p90
        return gyro_p90 < .22 and bool(np.all(flex_range <= self.quiet_flex_adc))

    def _refresh_baseline(self, stamp, duration_ms=300):
        recent = [item[1] for item in self.motion_history
                  if stamp - item[0] <= max(duration_ms, 100)]
        if recent:
            self.baseline_raw = np.median(np.stack(recent), axis=0)

    def push(self, row):
        stamp = float(row["timestamp"])
        if self.last_stamp is not None and not 0 < stamp - self.last_stamp <= 21:
            self.reset(wait_for_rest=True)
            raise ValueError("Mat mau/timestamp; giu tay dung yen roi thu lai")
        self.last_stamp = stamp
        try:
            validate_flex_row(row)
        except ValueError:
            self.reset(wait_for_rest=True)
            raise

        flex, gravity, gyro, accel = pose(row, self.reference)
        if not np.isfinite(np.r_[flex, gravity, gyro, accel]).all():
            self.reset(wait_for_rest=True)
            raise ValueError("Du lieu cam bien khong hop le; huy luot dang xet")

        raw_flex = self._raw_flex(row)
        at_rest = self._update_quiet_history(stamp, raw_flex, gyro)
        distance = float(np.max(np.abs(raw_flex - self.baseline_raw)))
        moving = bool(np.any(np.abs(raw_flex - self.baseline_raw) > self.start_flex_adc) or gyro > .3)
        self.last_distance = distance
        if self.last_gyro is None:
            self.last_gyro = gyro
        self.last_accel = accel
        self.last_at_rest = at_rest

        if self.state == "WAIT_REST":
            if at_rest:
                if self.rest_since is None:
                    self.rest_since = stamp
                elif stamp - self.rest_since >= 300:
                    self.state = "WAIT_START"
                    self._refresh_baseline(stamp)
                    self.rest_since = None
                    self.recent.clear()
            else:
                self.rest_since = None
            return None

        if self.state == "WAIT_START":
            if at_rest and not moving:
                if self.baseline_since is None:
                    self.baseline_since = stamp
                elif stamp - self.baseline_since >= 500:
                    self._refresh_baseline(stamp, 500)
            else:
                self.baseline_since = None
            if moving:
                if self.onset_since is None:
                    self.onset_since = stamp
                    self.onset_rows = list(self.recent)
                self.onset_rows.append(row)
                if stamp - self.onset_since >= 120:
                    self.state = "ACTIVE"
                    self.active_since = stamp
                    self.rest_since = None
                    self.recent.append(row)
                    return {"event": "start", "rows": list(self.onset_rows)}
            else:
                self.onset_since = None
                self.onset_rows = []
            self.recent.append(row)
            return None

        self.recent.append(row)
        if at_rest:
            if self.rest_since is None:
                self.rest_since = stamp
            elif (stamp - self.rest_since >= self.word_rest_ms and
                  stamp - self.active_since >= 1500):
                rest_start = self.rest_since
                self.state = "WAIT_START"
                self._refresh_baseline(stamp, self.word_rest_ms)
                self.baseline_since = stamp
                self.onset_since = None
                self.onset_rows = []
                self.rest_since = None
                self.active_since = None
                return {"event": "word_end", "timestamp": stamp, "rest_start": rest_start}
        else:
            self.rest_since = None
        return None


class StableWindowPredictor:
    """Use only contiguous, real 150-row windows accepted by the trained model."""

    def __init__(self, model, reference, step_ms=250):
        self.model = model
        self.reference = reference
        self.step_ms = step_ms
        self.rows = deque(maxlen=190)
        self.last_stamp = None
        self.last_prediction = None

    def reset(self):
        self.rows.clear()
        self.last_stamp = None
        self.last_prediction = None

    def update(self, rows):
        for row in rows:
            stamp = float(row["timestamp"])
            if self.last_stamp is not None and not 0 < stamp - self.last_stamp <= 20:
                self.reset()
            self.rows.append(row)
            self.last_stamp = stamp

        if len(self.rows) < 150:
            return None
        stamp = float(self.rows[-1]["timestamp"])
        if self.last_prediction is not None and stamp - self.last_prediction < self.step_ms:
            return None
        self.last_prediction = stamp

        history = list(self.rows)
        first_error = None
        for start in range(len(history) - 150, -1, -1):
            window = history[start:start + 150]
            duration = float(window[-1]["timestamp"]) - float(window[0]["timestamp"])
            if not 1490 <= duration <= 1510:
                continue
            try:
                quality = trial_quality(window, self.reference)
            except ValueError as error:
                if first_error is None:
                    first_error = str(error)
                continue
            return {
                "state": "RESULT",
                "label": self.model.predict(window, self.reference),
                "hz": quality["hz"],
                "timestamp": float(window[-1]["timestamp"]),
            }

        if first_error:
            return {"state": "ERROR", "reason": first_error}
        newest_duration = float(history[-1]["timestamp"]) - float(history[-150]["timestamp"])
        return {"state": "ERROR",
                "reason": f"Chua co cua so 150 mau hop le; khoang moi nhat {newest_duration:.1f} ms, can 1490..1510 ms"}


def collect_rest(stream, reference):
    print("GIU TAY O TU THE NGHI DE LAY MOC 2 GIAY...", flush=True)
    attempt = 0
    while True:
        try:
            return measure_rest(stream.capture(2.0)[-100:], reference)
        except ValueError as error:
            attempt += 1
            print(f"CHUA LAY DUOC MOC NGHI: {error}. Giu yen roi thu lai.", flush=True)
            if attempt % 3 == 0 and input("ENTER: do lai | Q: dung > ").strip().upper() == "Q":
                return None


def finish_word(votes):
    if not votes:
        return "CHUA_NHAN_DUOC", 0, 0
    counts = Counter(votes)
    label, count = counts.most_common(1)[0]
    if count / len(votes) < .5:
        return "CHUA_RO", count, len(votes)
    return label, count, len(votes)


WORD_TEXT = {
    "TOI": "TÔI",
    "CAM_ON": "CẢM ƠN",
    "BAN": "BẠN",
    "KHOE": "KHỎE",
    "KHONG": "KHÔNG",
    "XIN": "XIN",
    "CHAO": "CHÀO",
    "XIN_CHAO": "XIN CHÀO",
}

KNOWN_SENTENCES = {
    ("TOI", "CAM_ON", "BAN"): "TÔI CẢM ƠN BẠN",
    ("BAN", "KHOE"): "BẠN KHỎE KHÔNG",
    ("BAN", "KHOE", "KHONG"): "BẠN KHỎE KHÔNG",
    ("TOI", "KHOE"): "TÔI KHỎE",
    ("XIN", "CHAO"): "XIN CHÀO",
    ("XIN_CHAO",): "XIN CHÀO",
    # U4 has a CHAO word label, while the intended greeting phrase is XIN CHAO.
    ("CHAO",): "XIN CHÀO",
}


def clean_sentence_words(words):
    """Drop NONE and adjacent duplicate window decisions from one phrase."""
    cleaned = []
    for word in words:
        if word == "NONE":
            continue
        if not cleaned or cleaned[-1] != word:
            cleaned.append(word)
    return cleaned


def render_sentence(words):
    cleaned = clean_sentence_words(words)
    if not cleaned:
        return "(chưa nhận được câu)"
    known = KNOWN_SENTENCES.get(tuple(cleaned))
    if known:
        return known
    return " ".join(WORD_TEXT.get(word, word.replace("_", " ")) for word in cleaned)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial-port", default="COM3")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--word-rest-ms", type=int, default=300,
                        help="Stable rest between signs before committing one word")
    parser.add_argument("--sentence-pause-ms", "--end-pause-ms", dest="sentence_pause_ms", type=int, default=5000,
                        help="Stable rest after the last word before finalizing the sentence")
    parser.add_argument("--recalibrate", action="store_true")
    args = parser.parse_args(argv)
    if not 100 <= args.word_rest_ms <= 1500:
        parser.error("--word-rest-ms must be between 100 and 1500")
    if not 1000 <= args.sentence_pause_ms <= 15000:
        parser.error("--sentence-pause-ms must be between 1000 and 15000")

    stream = sock = None
    try:
        model = SequenceModel(args.model)
        if model.manifest.get("classifier") != "ExtraTreesClassifier":
            raise ValueError("Can model ExtraTrees U4; giu dung model U4 da train")
        if not {"BAN", "CAM_ON", "CHAO", "KHOE", "NONE", "TOI"}.issubset(model.manifest["labels"]):
            raise ValueError("Model thieu nhan U4 hoac NONE")

        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10)
        stream.check_ready()
        if args.recalibrate:
            reference = calibrate(stream)
            if reference is None:
                return 0
        else:
            reference = validate_reference(json.loads(latest_reference().read_text(encoding="utf-8")))
            print("MOC FLEX: dung moc gan nhat trong du lieu U4.", flush=True)
            reference = initialize_imu(stream, reference)

        rest = collect_rest(stream, reference)
        if rest is None:
            return 0

        boundary = MovementBoundary(reference, rest, args.word_rest_ms)
        detector = StableWindowPredictor(model, reference, step_ms=250)
        with stream.condition:
            cursor = stream.serial
        send_state(sock, "WAIT")
        print(f"MODEL: {args.model}", flush=True)
        print("NHAN LIEN TUC: tay bat dau cu dong la bat dau mot tu; tay dung yen la ket thuc tu.", flush=True)
        print(f"Chot tu sau {args.word_rest_ms} ms dung yen (can du cua so 1.5 giay de du doan).", flush=True)
        print(f"Neu khong co tu moi trong {args.sentence_pause_ms / 1000:g} giay, tu dong ket thuc cau.", flush=True)
        print("Moi tu can cua so 1.5 giay; Ctrl+C: dung.", flush=True)

        active = False
        votes = []
        sentence_words = []
        sentence_rest_since = None
        paused_during_word = False
        rest_notice = False
        active_since = None
        last_progress_at = time.monotonic()
        window_error_announced = False
        last_sensor_error_key = None
        stalled = False
        last_data = time.monotonic()
        while True:
            cursor, batch = stream.read_since(cursor, timeout=.25)
            if not batch:
                silence = time.monotonic() - last_data
                if silence > 3:
                    raise ValueError("Khong co mau moi trong 3 giay")
                if silence > .5 and not stalled:
                    boundary.reset(wait_for_rest=True)
                    detector.reset()
                    active = False
                    votes = []
                    paused_during_word = False
                    rest_notice = False
                    active_since = None
                    sentence_rest_since = None
                    stalled = True
                    print("MAT DU LIEU: huy luot dang xet, cho mau tro lai.", flush=True)
                continue

            last_data = time.monotonic()
            if stalled:
                stalled = False
                continue

            for row in batch:
                try:
                    boundary_event = boundary.push(row)
                except (ValueError, KeyError) as error:
                    boundary.reset(wait_for_rest=True)
                    detector.reset()
                    active = False
                    votes = []
                    paused_during_word = False
                    rest_notice = False
                    active_since = None
                    sentence_rest_since = None
                    message = str(error)
                    error_key = message.split(";", 1)[0].split(", ADC=", 1)[0]
                    if error_key != last_sensor_error_key:
                        print(f"DU LIEU LOI: {message}; chinh cam bien/GPIO hien tren, roi cho mau hop le.", flush=True)
                    last_sensor_error_key = error_key
                    continue

                if last_sensor_error_key is not None and boundary.state == "WAIT_START":
                    print("CAM BIEN HOP LE TRO LAI; san sang thu dong tac.", flush=True)
                    last_sensor_error_key = None

                if boundary_event and boundary_event["event"] == "start":
                    stamp = float(row["timestamp"])
                    if (sentence_rest_since is not None and
                            stamp - sentence_rest_since >= args.sentence_pause_ms):
                        if sentence_words:
                            print("KẾT QUẢ CÂU: " + render_sentence(sentence_words), flush=True)
                            print("CÂU ĐÃ CHỐT; sẵn sàng nhận câu mới.", flush=True)
                        sentence_words = []
                    sentence_rest_since = None
                    active = True
                    votes = []
                    paused_during_word = False
                    rest_notice = False
                    active_since = stamp
                    last_progress_at = time.monotonic()
                    window_error_announced = False
                    detector.reset()
                    print("BAT DAU: phat hien tay bat dau cu dong; dang lay cua so 1.5 giay.", flush=True)
                    event = detector.update(boundary_event["rows"])
                    if event and event["state"] == "RESULT":
                        votes.append(event["label"])
                    elif event and event["state"] == "ERROR" and not window_error_announced:
                        print(f"CUA SO CHUA HOP LE: {event['reason']}", flush=True)
                        window_error_announced = True
                    continue

                if boundary_event and boundary_event["event"] == "word_end":
                    final_event = detector.update([row])
                    if final_event and final_event["state"] == "RESULT":
                        votes.append(final_event["label"])
                    label, count, total = finish_word(votes)
                    if label in model.manifest["labels"] and label != "NONE":
                        sentence_words.append(label)
                        print(f"CÂU ĐANG GHÉP: {render_sentence(sentence_words)} "
                              f"| vừa nhận {WORD_TEXT.get(label, label.replace('_', ' '))} "
                              f"({count}/{total}) — câu còn mở {args.sentence_pause_ms / 1000:g} giây.", flush=True)
                    else:
                        print(f"CHƯA NHẬN RÕ TỪ: {WORD_TEXT.get(label, label.replace('_', ' '))} | {count}/{total} cửa sổ", flush=True)
                    send_result(sock, label)
                    send_state(sock, "WAIT")
                    active = False
                    votes = []
                    paused_during_word = False
                    rest_notice = False
                    active_since = None
                    window_error_announced = False
                    detector.reset()
                    sentence_rest_since = float(boundary_event["rest_start"])
                    continue

                if active:
                    if boundary.rest_since is not None:
                        if not rest_notice:
                            print(f"TAY TẠM DỪNG: vẫn đọc cảm biến; chờ {args.word_rest_ms} ms để chốt từ. Câu chưa kết thúc.", flush=True)
                            rest_notice = True
                    else:
                        rest_notice = False
                    event = detector.update([row])
                    if event and event["state"] == "RESULT":
                        votes.append(event["label"])
                        window_error_announced = False
                    elif event and event["state"] == "ERROR" and not window_error_announced:
                        print(f"CUA SO CHUA HOP LE: {event['reason']}; tiep tuc cho cua so that.", flush=True)
                        window_error_announced = True
                    if time.monotonic() - last_progress_at >= 2:
                        sample_count = min(len(detector.rows), 150)
                        print(f"DANG CHO: cua so {sample_count}/150 mau; so du doan tam {len(votes)}.", flush=True)
                        if (boundary.last_flex_range is not None and not boundary.last_at_rest and
                                active_since is not None and float(row["timestamp"]) - active_since >= 2000):
                            print(f"CHUA DUNG YEN: bien do flex lon nhat {np.max(boundary.last_flex_range):.1f} ADC "
                                  f"(nguong {np.max(boundary.quiet_flex_adc):.1f}); gyro {boundary.last_gyro:.2f} "
                                  f"(can < 0.22).", flush=True)
                        last_progress_at = time.monotonic()
                    continue

                # A new movement before the sentence timeout keeps words in
                # the same sentence; otherwise finalize on a sustained pause.
                if (sentence_rest_since is not None and boundary.onset_since is None and
                        float(row["timestamp"]) - sentence_rest_since >= args.sentence_pause_ms):
                    if sentence_words:
                        print("KẾT QUẢ CÂU: " + render_sentence(sentence_words), flush=True)
                        print("CÂU ĐÃ CHỐT; sẵn sàng nhận câu mới.", flush=True)
                    sentence_words = []
                    sentence_rest_since = None
    except (KeyboardInterrupt, EOFError):
        print("Da dung.", flush=True)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"DUNG: {error}", flush=True)
        return 1
    finally:
        if sock:
            try:
                send_state(sock, "OFF")
            except OSError:
                pass
        if stream:
            stream.close()
        elif sock:
            sock.close()


if __name__ == "__main__":
    raise SystemExit(main())
