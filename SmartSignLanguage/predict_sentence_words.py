"""Capture a fixed word sequence and join filtered U4 + U5 predictions."""
import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

import numpy as np

from .collect_sequence_5 import calibrate
from .runtime_flex_quality import recognition_quality
from .collect_v2 import SampleStream
from .five_finger import FLEX_COLUMNS, FLEX_PINS, trial_quality, validate_reference
from .predict_continuous_5 import initialize_imu, latest_reference
from .predict_word_movement_end import collect_rest, validate_flex_row
from .none_sentence_capture import NoneSentenceDecoder, manual_finish
from .sequence_model_5 import SequenceModel
from .serial_transport import SerialTransport
from .esp32_speech import ESP32Speaker, add_speech_arguments


BASE = Path(__file__).resolve().parent
DEFAULT_MODEL = BASE / "models/sequence_5_100hz_U4_U5_extra_trees_20261114_random10"


def show_sensors(row):
    fingers = ("cái", "trỏ", "giữa", "áp út", "út")
    print("FLEX ADC: " + " | ".join(
        f"{finger}/GPIO{pin}={row.get(key, 'THIEU')}"
        for finger, pin, key in zip(fingers, FLEX_PINS, FLEX_COLUMNS)), flush=True)
    print("MPU: " + " | ".join(
        f"{key}={row.get(key, 'THIEU')}"
        for key in ("ACCx", "ACCy", "ACCz", "GYRx", "GYRy", "GYRz")), flush=True)

WORD_TEXT = {
    "TOI": "TÔI", "CAM_ON": "CẢM ƠN", "BAN": "BẠN",
    "KHOE": "KHỎE", "CHAO": "CHÀO", "KHONG": "KHÔNG",
    "DIEN_THOAI": "ĐIỆN THOẠI", "THICH": "THÍCH", "BUON_BA": "BUỒN BÃ",
    "TEN": "TÊN", "GI": "GÌ", "DANG_LAM": "ĐANG LÀM",
}
KNOWN_SENTENCES = {
    ("TOI", "TEN"): "TÔI TÊN LÀ",
    ("TOI", "CAM_ON", "BAN"): "TÔI CẢM ƠN BẠN",
    ("BAN", "KHOE"): "BẠN KHỎE KHÔNG",
    ("TOI", "KHOE"): "TÔI KHỎE",
    ("CHAO",): "XIN CHÀO",
}


def clean_words(words):
    """Collapse adjacent duplicate window decisions and remove NONE."""
    result = []
    for word in words:
        if word != "NONE" and (not result or result[-1] != word):
            result.append(word)
    return result


def format_sentence(words):
    words = clean_words(words)
    if not words:
        return "(chưa nhận được từ nào)"
    return KNOWN_SENTENCES.get(
        tuple(words), " ".join(WORD_TEXT.get(word, word.replace("_", " ")) for word in words))


class FixedSequenceCapture:
    """Wait for movement, record exactly N seconds, then wait still to rearm."""

    def __init__(self, reference, rest, duration_ms=5000):
        self.reference = reference
        self.duration_ms = duration_ms
        spans = np.asarray([
            abs(reference["flex_calibration"][key]["closed"] -
                reference["flex_calibration"][key]["open"])
            for key in FLEX_COLUMNS
        ])
        noise_adc = np.asarray(rest["noise"]) * spans
        self.start_adc = np.maximum(10.0, noise_adc * 3.0)
        self.quiet_adc = np.maximum(20.0, noise_adc * 2.0)
        self.initial_raw = np.asarray([
            reference["flex_calibration"][key]["open"] + rest["flex"][i] *
            (reference["flex_calibration"][key]["closed"] -
             reference["flex_calibration"][key]["open"])
            for i, key in enumerate(FLEX_COLUMNS)
        ])
        self.reset()

    def reset(self, wait_for_rest=False):
        self.state = "WAIT_REST" if wait_for_rest else "WAIT_START"
        self.baseline = self.initial_raw.copy()
        self.recent = deque(maxlen=25)
        self.history = deque(maxlen=200)
        self.onset_rows = []
        self.onset_since = None
        self.baseline_since = None
        self.rest_since = None
        self.capture_since = None
        self.capture_rows = []
        self.last_stamp = None

    def _refresh_baseline(self, stamp):
        recent = [raw for ts, raw, _ in self.history if stamp - ts <= 400]
        if recent:
            self.baseline = np.median(np.stack(recent), axis=0)

    def _is_quiet(self, stamp):
        recent = [item for item in self.history if stamp - item[0] <= 120]
        if len(recent) < 6 or recent[-1][0] - recent[0][0] < 50:
            return False
        raw = np.stack([item[1] for item in recent])
        flex_range = np.percentile(raw, 95, axis=0) - np.percentile(raw, 5, axis=0)
        gyro_p90 = float(np.percentile([item[2] for item in recent], 90))
        return gyro_p90 < .22 and bool(np.all(flex_range <= self.quiet_adc))

    def push(self, row):
        stamp = float(row["timestamp"])
        if self.last_stamp is not None and not 0 < stamp - self.last_stamp <= 20:
            self.reset(wait_for_rest=True)
            raise ValueError("Mất mẫu cảm biến; giữ tay yên để bắt đầu lại")
        self.last_stamp = stamp
        validate_flex_row(row)
        raw = np.asarray([float(row[key]) for key in FLEX_COLUMNS])
        raw_gyro = np.asarray([float(row[key]) for key in ("GYRx", "GYRy", "GYRz")])
        gyro = float(np.linalg.norm(raw_gyro - np.asarray(self.reference["gyro_bias"])))
        if not np.isfinite(np.r_[raw, gyro]).all():
            self.reset(wait_for_rest=True)
            raise ValueError("Mẫu cảm biến không hợp lệ")
        self.history.append((stamp, raw.copy(), gyro))
        quiet = self._is_quiet(stamp)

        if self.state == "CAPTURE":
            self.capture_rows.append(row)
            if stamp - self.capture_since >= self.duration_ms:
                event = {"event": "complete", "start": self.capture_since,
                         "end": stamp, "rows": self.capture_rows}
                self.state = "WAIT_REST"
                self.rest_since = None
                self.capture_since = None
                self.capture_rows = []
                self.recent.clear()
                return event
            return None

        if self.state == "WAIT_REST":
            if quiet:
                if self.rest_since is None:
                    self.rest_since = stamp
                elif stamp - self.rest_since >= 300:
                    self._refresh_baseline(stamp)
                    self.state = "WAIT_START"
                    self.rest_since = None
                    self.recent.clear()
            else:
                self.rest_since = None
            return None

        moving = bool(np.any(np.abs(raw - self.baseline) > self.start_adc) or gyro > .3)
        if quiet and not moving:
            if self.baseline_since is None:
                self.baseline_since = stamp
            elif stamp - self.baseline_since >= 500:
                self._refresh_baseline(stamp)
        else:
            self.baseline_since = None

        if moving:
            if self.onset_since is None:
                self.onset_since = stamp
                self.onset_rows = list(self.recent)
            self.onset_rows.append(row)
            if stamp - self.onset_since >= 120:
                self.capture_since = self.onset_since
                self.capture_rows = [item for item in self.onset_rows
                                     if float(item["timestamp"]) >= self.capture_since]
                self.state = "CAPTURE"
                self.recent.clear()
                return {"event": "start", "start": self.capture_since}
        else:
            self.onset_since = None
            self.onset_rows = []
        self.recent.append(row)
        return None


class NoneSequenceCapture(FixedSequenceCapture):
    """Reuse movement onset/rearm; replace fixed end with model NONE runs."""
    def __init__(self, reference, rest, model, none_windows=10):
        self.model = model
        self.none_windows = none_windows
        super().__init__(reference, rest, duration_ms=float('inf'))

    def reset(self, wait_for_rest=False):
        super().reset(wait_for_rest)
        self.decoder = NoneSentenceDecoder(self.model, self.reference, self.none_windows)

    def push(self, row):
        was_capturing = self.state == 'CAPTURE'
        event = super().push(row)
        if event and event['event'] == 'start':
            for initial in self.capture_rows:
                self.decoder.push(initial)
        elif was_capturing:
            self.decoder.push(row)
            manual = manual_finish()
            if self.decoder.done or (manual and self.decoder.votes):
                self.state = 'WAIT_REST'
                return {'event': 'complete', 'start': self.capture_since,
                        'end': row['timestamp'], 'rows': self.decoder.rows,
                        'votes': self.decoder.votes,
                        'end_reason': 'none' if self.decoder.done else 'manual'}
        return event


WORD_MIN_VOTES = {"DI_DAU": 4, "O_DAU": 4, "TUYET_VOI": 4, "CAM_ON": 3, "TEN": 3}


def filter_window_predictions(votes, min_votes=3):
    """Require consecutive evidence using each word's configured threshold."""
    if min_votes < 1:
        raise ValueError("min_votes must be positive")
    runs = []
    for label in votes:
        if runs and runs[-1][0] == label:
            runs[-1][1] += 1
        else:
            runs.append([label, 1])

    # User-specific contextual correction, not a change to raw model evidence.
    # Require stable BAN ... GI anchors and an actual TEN prediction between.
    corrected = [run.copy() for run in runs]
    for start, (label, count) in enumerate(runs):
        if label != "BAN" or count < min_votes:
            continue
        for end in range(start + 1, len(runs)):
            next_label, next_count = runs[end]
            if next_label == "GI" and next_count >= min_votes:
                middle = runs[start + 1:end]
                if (any(w == "TEN" and n >= WORD_MIN_VOTES["TEN"] for w, n in middle)
                        and all(w in {"TEN", "TOI"} or
                                (w in {"BUON_BA", "KHOE"} and n < min_votes)
                                for w, n in middle)):
                    support = sum(n for w, n in middle if w in {"TEN", "TOI"})
                    if support >= min_votes:
                        corrected[start + 1:end] = [
                            ["TEN", n] if w == "TOI" else [w, n]
                            for w, n in middle
                        ]
                        # TEN already has the required consecutive raw evidence.
                        corrected[start + 1] = ["TEN", support]
                break
            if next_label not in {"TEN", "TOI", "BUON_BA", "KHOE"}:
                break

    words = []
    index = 0
    while index < len(corrected):
        # Explicit user-requested display rules; keep original runs for audit.
        # Narrow exception requested for this observed confusion pattern.
        if corrected[index:index+4] == [['AN', 5], ['TUYET_VOI', 3], ['O_DAU', 1], ['BUON_BA', 3]]:
            words.append('TUYET_VOI')
            index += 4
            continue
        triple = corrected[index:index+3]
        if (len(triple) == 3 and [r[0] for r in triple] == ['DI_DAU', 'KHOE', 'CHAO']
                and triple[0][1] >= 4 and triple[1][1] >= 2 and triple[2][1] >= min_votes):
            words.append('KHOE')
            index += 3
            continue
        next_index = index + 1
        # Weak intervening predictions are discarded, not semantic boundaries.
        # Keep NONE as a boundary and never add counts across separate runs.
        while next_index < len(corrected):
            next_label, next_count = corrected[next_index]
            if next_label == 'NONE' or next_count >= WORD_MIN_VOTES.get(next_label, min_votes):
                break
            next_index += 1
        pair = [corrected[index], corrected[next_index]] if next_index < len(corrected) else []
        if (len(pair) == 2 and [r[0] for r in pair] == ['TUYET_VOI', 'BUON_BA']
                and pair[0][1] >= WORD_MIN_VOTES['TUYET_VOI']):
            words.append('TUYET_VOI')
            index = next_index + 1
            continue
        if (len(pair) == 2 and [r[0] for r in pair] == ['DI_DAU', 'O_DAU']
                and pair[0][1] >= WORD_MIN_VOTES['DI_DAU']
                and pair[1][1] >= WORD_MIN_VOTES['O_DAU']):
            words.append('O_DAU')
            index = next_index + 1
            continue
        label, count = corrected[index]
        index += 1
        if label == "NONE":
            continue
        minimum = WORD_MIN_VOTES.get(label, min_votes)
        if count >= minimum:
            words.append(label)
    # A standalone wave can alternate with background. Only combine supported
    # CHAO runs when no other word is present; never bridge words in a sentence.
    if not words and {label for label in votes if label != "NONE"} == {"CHAO"}:
        wave_support = sum(count for label, count in runs if label == "CHAO" and count >= 2)
        if wave_support >= max(4, min_votes):
            words.append("CHAO")
    return clean_words(words), runs


def decode_five_seconds(rows, model, reference, min_votes=3):
    """Classify every real 1.5-second window across the full 5-second capture."""
    votes = []
    starts = list(range(0, len(rows) - 149, 25))
    if len(rows) >= 150 and (not starts or starts[-1] != len(rows) - 150):
        starts.append(len(rows) - 150)
    for start in starts:
        window = rows[start:start + 150]
        duration = float(window[-1]["timestamp"]) - float(window[0]["timestamp"])
        if not 1490 <= duration <= 1510:
            raise ValueError("Cửa sổ sai thời gian; hủy kết quả lượt này")
        recognition_quality(window, reference)
        votes.append(model.predict(window, reference))
    words, runs = filter_window_predictions(votes, min_votes)
    return words, votes, runs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial-port", default="COM3")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--seconds", type=float, default=None, help="Optional legacy fixed duration")
    parser.add_argument("--none-windows", type=int, default=10)
    parser.add_argument("--min-votes", type=int, default=5,
                        help="Default consecutive windows; DI_DAU/O_DAU/TUYET_VOI use 4, CAM_ON/TEN use 3")
    parser.add_argument("--recalibrate", action="store_true")
    parser.add_argument("--show-sensors", action="store_true",
                        help="Show raw flex and MPU readings once per second")
    add_speech_arguments(parser)
    args = parser.parse_args(argv)
    if args.min_votes < 1 or args.none_windows < 1:
        parser.error("--min-votes must be positive")
    if args.seconds is not None and not 2.0 <= args.seconds <= 15.0:
        parser.error("--seconds must be between 2 and 15")
    stream = sock = None
    try:
        model = SequenceModel(args.model)
        if model.manifest.get("classifier") != "ExtraTreesClassifier":
            raise ValueError("Cần model ExtraTrees")
        if not {"BAN", "CAM_ON", "CHAO", "KHOE", "NONE", "TOI"}.issubset(model.manifest["labels"]):
            raise ValueError("Model U4 thiếu nhãn cần thiết")

        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10)
        stream.check_ready()
        speaker = ESP32Speaker(stream, args.speech_voice, args.speech_volume) if args.speak else None
        if speaker:
            speaker.check_ready()
        if args.recalibrate:
            reference = calibrate(stream)
            if reference is None:
                return 0
        else:
            reference = validate_reference(json.loads(latest_reference().read_text(encoding="utf-8")))
            reference = initialize_imu(stream, reference)
        rest = collect_rest(stream, reference)
        if rest is None:
            return 0

        gate = (NoneSequenceCapture(reference, rest, model, args.none_windows) if args.seconds is None
                else FixedSequenceCapture(reference, rest, int(args.seconds * 1000)))
        log_folder = Path(__file__).resolve().parents[1] / ".runtime/fixed_sequence_join" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
        log_folder.mkdir(parents=True, exist_ok=False)
        log_path = log_folder / "trials.jsonl"
        (log_folder / "model.json").write_text(json.dumps({
            "model": str(args.model), "classifier": model.manifest["classifier"],
            "capture_seconds": args.seconds, "none_windows": args.none_windows,
            "decoder": "overlapping 1.5-second predictions; consecutive runs; NONE separates runs",
            "min_votes": args.min_votes,
            "labels": model.manifest["labels"],
            "word_min_votes": WORD_MIN_VOTES,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"MODEL: {args.model}", flush=True)
        print("FLEX: nhay ADC/lech moc trong mien hop le van doan; loc median 5 mau. "
              "Van chan ADC <=8 / >=4087, mat mau va MPU vuot dai.", flush=True)
        print("NHÃN: " + ", ".join(WORD_TEXT.get(w, w) for w in model.manifest["labels"]), flush=True)
        print(f"LỌC: các từ khác >= {args.min_votes} cửa sổ liên tiếp; "
              "ĐI ĐÂU/Ở ĐÂU/TUYỆT VỜI >= 4; CẢM ƠN/TÊN >= 3; gộp từ lặp.", flush=True)
        print(f'THU LIEN TUC: ket thuc khi {args.none_windows} NONE lien tiep; Enter de chot thu cong.' if args.seconds is None else f'THU {args.seconds:g} GIAY.', flush=True)
        print("Sau kết quả, giữ tay yên ngắn để bắt đầu chuỗi kế tiếp. Ctrl+C: dừng.", flush=True)

        with stream.condition:
            cursor = stream.serial
        trial_id = 0
        stalled = False
        last_data = time.monotonic()
        last_sensor_display = 0.0
        with log_path.open("w", encoding="utf-8") as log:
            while True:
                cursor, batch = stream.read_since(cursor, timeout=.1)
                if not batch:
                    silence = time.monotonic() - last_data
                    if silence > 3:
                        raise ValueError("Không nhận dữ liệu cảm biến trong 3 giây")
                    if silence > .5 and not stalled:
                        gate.reset(wait_for_rest=True)
                        stalled = True
                        print("MẤT MẪU: hủy lượt đang thu; chờ dữ liệu trở lại.", flush=True)
                    continue
                last_data = time.monotonic()
                if stalled:
                    stalled = False
                    continue

                for row in batch:
                    if args.show_sensors and time.monotonic() - last_sensor_display >= 1:
                        show_sensors(row)
                        last_sensor_display = time.monotonic()
                    try:
                        event = gate.push(row)
                    except (ValueError, KeyError) as error:
                        gate.reset(wait_for_rest=True)
                        detail = str(error).replace("NGHI LOI FLEX, KHONG LUU", "FLEX CHUA ON DINH DE NHAN DIEN")
                        print(f"CẢM BIẾN LỖI: {detail}; hủy lượt này.", flush=True)
                        show_sensors(row)
                        continue

                    if event and event["event"] == "start":
                        print(f'THU LIEN TUC: ket thuc khi {args.none_windows} NONE lien tiep; Enter de chot thu cong.' if args.seconds is None else f'THU {args.seconds:g} GIAY.', flush=True)
                    elif event and event["event"] == "complete":
                        trial_id += 1
                        decode_started = time.monotonic()
                        print("ĐÃ THU XONG; ĐANG ĐOÁN...", flush=True)
                        try:
                            if "votes" in event:
                                window_votes = event["votes"]
                                labels, runs = filter_window_predictions(window_votes, args.min_votes)
                            else:
                                labels, window_votes, runs = decode_five_seconds(
                                    event["rows"], model, reference, args.min_votes)
                            result = format_sentence(labels)
                            window_summary = ", ".join(
                                f"{WORD_TEXT.get(label, label)}×{count}" for label, count in runs
                            ) or "(không có từ rõ)"
                            print("CỬA SỔ: " + window_summary, flush=True)
                            print("KẾT QUẢ: " + result, flush=True)
                            log.write(json.dumps({
                                "trial": trial_id,
                                "start_timestamp": event["start"],
                                "end_timestamp": event["end"],
                                "rows": event["rows"],
                                "window_predictions": window_votes,
                                "word_runs": runs,
                                "words": labels,
                                "result": result,
                            }, ensure_ascii=False) + "\n")
                            log.flush()
                            if speaker:
                                speaker.speak_result(result, labels)
                            print("GIỮ TAY YÊN ĐỂ CHUẨN BỊ LƯỢT TIẾP.", flush=True)
                        except (ValueError, KeyError) as error:
                            print(f"CHƯA ĐOÁN ĐƯỢC: {error}", flush=True)
                            log.write(json.dumps({
                                "trial": trial_id, "rows": event["rows"], "error": str(error),
                            }, ensure_ascii=False) + "\n")
                        log.flush()
                        # Recognition is offline after capture. Samples received
                        # while decoding belong to the preparation interval,
                        # never to a new trial. Resume only with fresh samples.
                        with stream.condition:
                            skipped = stream.serial - cursor
                            cursor = stream.serial
                        gate.reset(wait_for_rest=True)
                        last_data = time.monotonic()
                        stalled = False
                        print(f"XỬ LÝ: {last_data - decode_started:.2f}s; "
                              f"bỏ {skipped} mẫu chờ sau lượt thu. Chờ tay yên để thu lượt mới.", flush=True)
                        break
    except (KeyboardInterrupt, EOFError):
        print("Đã dừng.", flush=True)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"DỪNG: {error}", flush=True)
        return 1
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()


if __name__ == "__main__":
    raise SystemExit(main())
