"""Join U4 words from one continuous stream using the temporal word HMM."""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

import joblib
import numpy as np

from .ctc_utterance import pose
from .predict_join_hmm import SensorFrames
from .sequence_hmm import OnlineWordHMM, WordHMM
from .collect_sequence_5 import calibrate
from .collect_v2 import SampleStream
from .sequence_model_5 import FLEX_COLUMNS
from .serial_transport import SerialTransport


def measure_rest(rows, reference):
    raw = np.asarray([[float(r[k]) for k in FLEX_COLUMNS] for r in rows])
    if len(raw) < 50 or not np.isfinite(raw).all() or np.any(raw <= 8) or np.any(raw >= 4087):
        raise ValueError('Du lieu moc nghi khong du hoac flex loi/bao hoa')
    poses = [pose(r, reference) for r in rows]
    gyro = np.asarray([p[2] for p in poses])
    if np.percentile(gyro, 95) > .5:
        raise ValueError('Tay con chuyen dong khi lay moc nghi; giu yen de do lai')
    flex = np.stack([p[0] for p in poses])
    noise = np.percentile(flex, 95, axis=0) - np.percentile(flex, 5, axis=0)
    return {'flex': np.median(flex, axis=0).tolist(), 'flex_noise_p90': noise.tolist()}


def collect_rest(stream, reference):
    print('GIU TAY O TU THE NGHI; lay moc trong 2 giay...', flush=True)
    attempt = 0
    while True:
        try:
            return measure_rest(stream.capture(2.0)[-100:], reference)
        except ValueError as error:
            attempt += 1
            print(f'CHUA LAY DUOC MOC NGHI: {error}. Giu yen de do lai.', flush=True)
            if attempt % 3 == 0 and input('ENTER: do lai | Q: dung > ').strip().upper() == 'Q':
                return None


class PhraseBoundary:
    """Mark a whole phrase from departure from rest to a sustained return."""

    def __init__(self, reference, rest, start_ms=120, end_ms=1500):
        self.reference, self.rest = reference, rest
        noise = np.asarray(rest['flex_noise_p90'])
        self.start_flex = float(np.clip(max(.40, np.max(noise) * 2.5), .40, .80))
        self.rest_flex = float(np.clip(max(.25, np.max(noise) * 1.5), .25, .45))
        self.start_ms, self.end_ms = start_ms, end_ms
        self.reset()

    def reset(self, wait_for_rest=False):
        self.state = 'WAIT_REST' if wait_for_rest else 'WAIT_START'
        self.recent = deque(maxlen=25)
        self.onset_rows = []
        self.onset_since = None
        self.rest_since = None
        self.last_stamp = None

    def push(self, row):
        stamp = float(row['timestamp'])
        if self.last_stamp is not None and not 0 < stamp - self.last_stamp <= 21:
            self.reset(wait_for_rest=True)
            raise ValueError('Mat mau/timestamp trong bo tach bat dau-ket thuc')
        self.last_stamp = stamp
        raw = np.asarray([float(row[k]) for k in FLEX_COLUMNS])
        if not np.isfinite(raw).all() or np.any(raw <= 8) or np.any(raw >= 4087):
            self.reset(wait_for_rest=True)
            raise ValueError('Flex loi/bao hoa; huy luot dang xet')
        flex, _, gyro, accel = pose(row, self.reference)
        if not np.isfinite(np.r_[flex, gyro, accel]).all():
            self.reset(wait_for_rest=True)
            raise ValueError('Du lieu cam bien khong hop le; huy luot dang xet')

        distance = float(np.max(np.abs(flex - np.asarray(self.rest['flex']))))
        active = distance > self.start_flex or gyro > .65 or accel > 2.5
        at_rest = distance < self.rest_flex and gyro < .25 and accel < 1.2

        if self.state == 'WAIT_REST':
            if at_rest:
                if self.rest_since is None:
                    self.rest_since = stamp
                if stamp - self.rest_since >= 300:
                    self.state = 'WAIT_START'
                    self.rest_since = None
                    self.recent.clear()
            else:
                self.rest_since = None
            return None

        if self.state == 'WAIT_START':
            if active:
                if self.onset_since is None:
                    self.onset_since = stamp
                    self.onset_rows = list(self.recent)
                self.onset_rows.append(row)
                if stamp - self.onset_since >= self.start_ms:
                    self.state = 'ACTIVE'
                    self.rest_since = None
                    self.recent.append(row)
                    return {'event': 'phrase_start', 'timestamp': stamp,
                            'rows': list(self.onset_rows)}
            else:
                self.onset_since = None
                self.onset_rows = []
            self.recent.append(row)
            return None

        self.recent.append(row)
        if at_rest:
            if self.rest_since is None:
                self.rest_since = stamp
            if stamp - self.rest_since >= self.end_ms:
                event = {'event': 'phrase_end', 'timestamp': stamp}
                self.state = 'WAIT_START'
                self.onset_since = None
                self.onset_rows = []
                self.rest_since = None
                return event
        else:
            self.rest_since = None
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    parser.add_argument('--model', type=Path,
                        default=Path(__file__).resolve().parent / 'models/word_hmm_u4_phrases_v2')
    parser.add_argument('--sentence-pause-ms', type=int, default=1500)
    parser.add_argument('--word-commit-ms', type=int, default=600,
                        help='Wait after a word completes on the best HMM path before committing an unresolved branch; lower is faster but can add false words')
    parser.add_argument('--repeat-rearm-ms', type=int, default=1200,
                        help='Stable background time needed before the same word can repeat')
    args = parser.parse_args()
    if not 100 <= args.word_commit_ms <= 3000:
        parser.error('--word-commit-ms must be between 100 and 3000')

    stream = sock = None
    try:
        model_path = args.model / 'model.joblib'
        model = joblib.load(model_path)
        if (not isinstance(model, WordHMM) or len(model.center) != 19 or
                set(model.labels) != {'TOI', 'CAM_ON', 'BAN', 'KHOE', 'CHAO'}):
            raise ValueError('Can model HMM U4 du 19 dac trung, dung 5 tu')
        decoder = OnlineWordHMM(model, fallback_commit_ms=args.word_commit_ms)

        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10)
        stream.check_ready()
        reference = calibrate(stream)
        if reference is None:
            return 0
        rest = collect_rest(stream, reference)
        if rest is None:
            return 0
        boundary = PhraseBoundary(reference, rest, end_ms=args.sentence_pause_ms)
        frame_builder = SensorFrames(reference)

        folder = Path(__file__).resolve().parents[1] / '.runtime/continuous_word_join' / (
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        (folder / 'reference.json').write_text(json.dumps(reference, indent=2), encoding='utf-8')
        (folder / 'rest.json').write_text(json.dumps(rest, indent=2), encoding='utf-8')
        (folder / 'model.json').write_text(json.dumps({
            'path': str(model_path),
            'sha256': hashlib.sha256(model_path.read_bytes()).hexdigest(),
            'labels': model.labels,
            'features': len(model.center),
            'decoder': 'continuous temporal HMM inside rest-to-rest phrase boundaries',
            'sentence_pause_ms': args.sentence_pause_ms,
            'repeat_rearm_ms': args.repeat_rearm_ms,
            'fallback_commit_ms': args.word_commit_ms,
            'note': 'Model is experimental; HMM scores are not calibrated probabilities.'
        }, indent=2), encoding='utf-8')

        print('TRANG THAI: CHO BAT DAU - giu tay o tu the nghi.', flush=True)
        print('BAT DAU CAU: chuyen dong ro lien tuc 120 ms; tu trong cau van ghep lien tuc.', flush=True)
        print('KET THUC CAU: tro ve tu the nghi va giu on dinh theo bo dem.', flush=True)
        print('Model theo doi dien bien cua ca chuoi; khong dem moi cua so lap lai nhu xac nhan doc lap.', flush=True)
        print(f'Giai ma nhanh: cho {args.word_commit_ms} ms sau moc ket thuc tu tren nhanh tot nhat neu cac nhanh chua dong thuan.', flush=True)
        print('Tu ngan nhu CAM ON duoc xet theo ca mau, khong bi bo chi vi chi hien mot vai khung.', flush=True)
        print('Ket qua van phu thuoc do chinh xac cua model; mot nhan chen co the con bi nham.', flush=True)
        print(f'Dung yen {args.sentence_pause_ms / 1000:g} giay de ket thuc cau.', flush=True)
        print('ENTER: chot cau | R: xoa chuoi | Ctrl+C: dung.', flush=True)
        print(f'LOG: {folder}', flush=True)

        import msvcrt
        with stream.condition:
            cursor = stream.serial
        words = []
        rest_since = None
        repeat_armed = True
        active = False
        bad = False
        stalled = False
        last_data = time.monotonic()
        with (folder / 'stream.jsonl').open('w', encoding='utf-8') as log:
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key == '\x03':
                        raise KeyboardInterrupt
                    if key.lower() == 'r' or key == '\r':
                        if key == '\r':
                            print('KET QUA CHOT TAY: ' + (' '.join(w.replace('_', ' ') for w in words) or '(chua nhan duoc tu)'), flush=True)
                            log.write(json.dumps({'event': 'manual_finish', 'words': words}) + '\n')
                        else:
                            log.write(json.dumps({'event': 'manual_reset', 'words': words}) + '\n')
                            print('DA XOA CHUOI.', flush=True)
                        words = []
                        repeat_armed = True
                        decoder.reset()
                        frame_builder.reset()
                        boundary.reset(wait_for_rest=True)
                        active = False
                        rest_since = None
                        with stream.condition:
                            cursor = stream.serial

                cursor, batch = stream.read_since(cursor, timeout=.1)
                if not batch:
                    silence = time.monotonic() - last_data
                    if silence > 3:
                        raise ValueError('Khong nhan du lieu trong 3 giay')
                    if silence > .5 and not stalled:
                        decoder.reset()
                        frame_builder.reset()
                        boundary.reset(wait_for_rest=True)
                        active = False
                        rest_since = None
                        words = []
                        repeat_armed = True
                        stalled = True
                        log.write(json.dumps({'event': 'data_stall'}) + '\n')
                        log.flush()
                        print('MAT DU LIEU: huy chuoi dang ghep, cho mau tro lai.', flush=True)
                    continue

                last_data = time.monotonic()
                if stalled:
                    stalled = False
                    continue
                for row in batch:
                    try:
                        boundary_event = boundary.push(row)
                    except (ValueError, KeyError) as exc:
                        error = str(exc)
                        decoder.reset()
                        frame_builder.reset()
                        boundary.reset(wait_for_rest=True)
                        active = False
                        rest_since = None
                        if not bad:
                            print('DU LIEU LOI: ' + error + '; xoa chuoi dang ghep.', flush=True)
                        words = []
                        repeat_armed = True
                        bad = True
                        log.write(json.dumps({'event': 'sensor_error', 'message': error}) + '\n')
                        continue

                    if boundary_event and boundary_event['event'] == 'phrase_start':
                        active = True
                        words = []
                        rest_since = None
                        repeat_armed = True
                        decoder.reset()
                        frame_builder.reset()
                        frame_rows = boundary_event.pop('rows')
                        print('BAT DAU CAU: phat hien tay roi tu the nghi.', flush=True)
                        log.write(json.dumps(boundary_event) + '\n')
                    elif active:
                        frame_rows = [row]
                    else:
                        log.write(json.dumps({'row': row, 'event': 'waiting_for_start'}) + '\n')
                        continue

                    for frame_row in frame_rows:
                        event = None
                        try:
                            frame = frame_builder.push(frame_row)
                            if frame is not None:
                                event = decoder.push(frame, frame_row['timestamp'])
                        except (ValueError, KeyError) as exc:
                            error = str(exc)
                            decoder.reset()
                            frame_builder.reset()
                            boundary.reset(wait_for_rest=True)
                            active = False
                            words = []
                            repeat_armed = True
                            rest_since = None
                            if not bad:
                                print('DU LIEU LOI: ' + error + '; huy cau dang thu.', flush=True)
                            bad = True
                            log.write(json.dumps({'event': 'sensor_error', 'message': error}) + '\n')
                            break
                        if event is not None and bad:
                            print('DA CO MAU HOP LE TRO LAI.', flush=True)
                            bad = False
                        if event is None:
                            log.write(json.dumps({'row': frame_row, 'prediction': None}) + '\n')
                            continue

                        stamp = float(frame_row['timestamp'])
                        stable_background = event['background_best'] and not event['pending_best']
                        if stable_background:
                            if rest_since is None:
                                rest_since = stamp
                            if stamp - rest_since >= args.repeat_rearm_ms:
                                repeat_armed = True
                        else:
                            rest_since = None

                        joined = []
                        suppressed = []
                        for label in event['words']:
                            if words and label == words[-1] and not repeat_armed:
                                suppressed.append(label)
                                continue
                            words.append(label)
                            joined.append(label)
                            repeat_armed = False
                        if joined:
                            if event.get('forced_commit'):
                                print('TU TAM CHOT (cac nhanh chua dong thuan): ' + ' '.join(w.replace('_', ' ') for w in joined), flush=True)
                            else:
                                print('TU DA CHOT: ' + ' '.join(w.replace('_', ' ') for w in joined), flush=True)
                            print('CHUOI HIEN TAI: ' + ' '.join(w.replace('_', ' ') for w in words), flush=True)
                        if suppressed:
                            print('GOP NHAN LAP LIEN TUC: ' + ' '.join(w.replace('_', ' ') for w in suppressed), flush=True)
                        event['joined_words'] = joined
                        event['suppressed_repeats'] = suppressed
                        log.write(json.dumps({'row': frame_row, 'prediction': event}) + '\n')

                    if boundary_event and boundary_event['event'] == 'phrase_end' and active:
                        result = ' '.join(w.replace('_', ' ') for w in words) or '(chua nhan duoc tu nao)'
                        print('KET THUC CAU: tay ve tu the nghi.', flush=True)
                        print('KET QUA CUOI CAU: ' + result, flush=True)
                        log.write(json.dumps({'event': 'sentence_finish', 'words': words,
                                              'timestamp': boundary_event['timestamp'],
                                              'background_label': 'NONE'}) + '\n')
                        words = []
                        repeat_armed = True
                        decoder.reset()
                        frame_builder.reset()
                        rest_since = None
                        active = False
                        log.write(json.dumps(boundary_event) + '\n')
                log.flush()
    except (KeyboardInterrupt, EOFError):
        print('Da dung.', flush=True)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f'DUNG: {error}', flush=True)
        return 1
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()


if __name__ == '__main__':
    raise SystemExit(main())
