"""Experimental live CTC word stream, with no required pause between words."""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
import numpy as np
import torch
from .train_word_ctc import Network, LABELS, features, decode
from .sequence_model_5 import FLEX_COLUMNS, legacy
from .collect_sequence_5 import calibrate
from .collect_v2 import SampleStream
from .serial_transport import SerialTransport
from .ctc_utterance import UtteranceCTC, rest_profile


class LiveCTC:
    def __init__(self, checkpoint, reference):
        if checkpoint['schema'] != 'causal-gru-ctc-five-flex-v1' or checkpoint['labels'] != LABELS:
            raise ValueError('Model CTC khong tuong thich')
        self.model = Network().eval()
        self.model.load_state_dict(checkpoint['state_dict'])
        self.mean = np.asarray(checkpoint['mean'], dtype=np.float32)
        self.std = np.asarray(checkpoint['std'], dtype=np.float32)
        if self.mean.shape != (19,) or self.std.shape != (19,) or not np.isfinite(self.mean).all() or not np.isfinite(self.std).all() or np.any(self.std <= 0):
            raise ValueError('Sai thong so chuan hoa')
        self.reference = reference
        self.reset()

    def reset(self):
        self.raw = deque(maxlen=5)
        self.block = []
        self.previous_flex = self.stamp = self.hidden = None
        self.previous_id = 0
        self.words = deque(maxlen=40)

    def feature(self, row):
        stamp = float(row['timestamp'])
        dt = None if self.stamp is None else (stamp-self.stamp)/1000
        if not np.isfinite(stamp) or (dt is not None and not 0 < dt <= .021):
            raise ValueError('Mat mau/reset timestamp; dung va chay lai')
        keys = (*FLEX_COLUMNS, 'ACCx','ACCy','ACCz','GYRx','GYRy','GYRz', *legacy.BODY_COLUMNS)
        x = np.array([float(row[k]) for k in keys])
        if not np.isfinite(x).all() or np.any(x[:5] <= 8) or np.any(x[:5] >= 4087):
            raise ValueError('Du lieu cam bien loi/bao hoa')
        self.raw.append(x[:5])
        flex = np.median(self.raw, axis=0)
        for i,k in enumerate(FLEX_COLUMNS):
            c = self.reference['flex_calibration'][k]
            flex[i] = (flex[i]-c['open'])/(c['closed']-c['open'])
        velocity = np.zeros(5) if dt is None else (flex-self.previous_flex)/dt
        self.previous_flex, self.stamp = flex.copy(), stamp
        self.block.append(np.concatenate((flex, (x[5:8]-x[11:14])/self.reference['gravity'],
                                          x[8:11]-self.reference['gyro_bias'], x[11:14], velocity)))
        if len(self.block) < 4:
            return None
        result = np.mean(self.block, axis=0).astype(np.float32)
        self.block.clear()
        return result

    def push(self, row):
        feature = self.feature(row)
        if feature is None:
            return None
        x = torch.tensor((feature-self.mean)/self.std)[None,None]
        with torch.inference_mode():
            output, self.hidden = self.model.gru(x, self.hidden)
            index = int(self.model.head(output)[0,0].argmax())
        emitted = LABELS[index] if index and index != self.previous_id else None
        self.previous_id = index
        if emitted:
            self.words.append(emitted)
        return {'timestamp': self.stamp, 'frame_label': LABELS[index], 'emitted': emitted}


class WindowCTC(LiveCTC):
    """Replace a rolling preview; never concatenate overlapping predictions."""
    def reset(self):
        super().reset()
        self.window = deque(maxlen=300)
        self.samples_since_prediction = 0

    def push(self, row):
        # Retain streaming validation, including gaps and saturation checks.
        self.feature(row)
        self.window.append(row)
        self.samples_since_prediction += 1
        if len(self.window) < 300 or self.samples_since_prediction < 25:
            return None
        self.samples_since_prediction = 0
        x = torch.tensor((features(list(self.window), self.reference)-self.mean)/self.std)[None]
        with torch.inference_mode():
            ids = self.model(x)[0].argmax(-1).tolist()
        words = decode(ids)
        self.words = deque(words, maxlen=40)
        return {'timestamp':row['timestamp'], 'preview':words,
                'window_start':self.window[0]['timestamp'], 'emitted':None}


def acquire_rest(stream, reference, prompt=input):
    print('GIU TU THE NGHI THOAI MAI; cho flex hoi on dinh. Khong can gap/duoi lai.',flush=True)
    attempt = 0
    while True:
        # First second lets the hand settle; measure the last second only.
        rows = stream.capture(2.0)
        try:
            profile = rest_profile(rows[-100:], reference)
        except ValueError as error:
            attempt += 1
            print(f'CHUA LAY DUOC MOC NGHI: {error}. Se do lai, giu nguyen tay.',flush=True)
            if attempt % 3 == 0:
                if prompt('ENTER: tiep tuc do moc nghi (giu hieu chuan cu) | Q: dung > ').strip().upper() == 'Q':
                    return None
            continue
        print('DAT MOC NGHI. Bat dau nhan dien.',flush=True)
        return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    parser.add_argument('--model', type=Path, default=Path(__file__).resolve().parent/'models/word_ctc_u4_phrases_v1')
    parser.add_argument('--preview', action='store_true', help='Diagnostic only: show unstable rolling windows instead of joining turns')
    args = parser.parse_args()
    stream = sock = None
    torch.set_num_threads(2)
    try:
        model_file = args.model/'model.pt'
        checkpoint = torch.load(model_file, map_location='cpu', weights_only=True)
        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10)
        stream.check_ready()
        reference = calibrate(stream)
        if reference is None:
            return 0
        loaded = LiveCTC(checkpoint, reference)
        print('GIU NGUYEN TU THE NGHI SAU HIEU CHUAN: dang lay moc ket thuc luot...',flush=True)
        rest = acquire_rest(stream, reference)
        if rest is None:
            return 0
        detector = WindowCTC(checkpoint, reference) if args.preview else UtteranceCTC(
            loaded.model, loaded.mean, loaded.std, reference, rest)
        folder = Path(__file__).resolve().parents[1]/'.runtime/ctc_live'/(
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        (folder/'reference.json').write_text(json.dumps(reference,indent=2),encoding='utf-8')
        (folder/'model.json').write_text(json.dumps({'path':str(model_file.resolve()),
            'sha256':hashlib.sha256(model_file.read_bytes()).hexdigest(),
            'mode':'preview' if args.preview else 'fixed_origin_turn', 'rest_profile':rest,
            'min_token_score':.70}),encoding='utf-8')
        with stream.condition:
            cursor = stream.serial
        print('SAN SANG: lam lien tuc cac tu; chi ve tu the nghi ban dau va giu 1 giay khi HET LUOT.',flush=True)
        print('THU NGHIEM: model con yeu; ket qua co the sai. Khong doc thanh tieng.',flush=True)
        if args.preview:
            print('CHAN DOAN CUA SO TRUOT: ket qua se thay doi, khong phai che do ghep.',flush=True)
        else:
            print('Moi luot toi da 8 giay. Khong can nghi giua cac tu. Chi hien ket qua khi het luot.',flush=True)
        print('R: xoa chuoi va khoi tao lai model khi muon thu luot moi. Ctrl+C: dung.',flush=True)
        print(f'LOG: {folder}',flush=True)
        import msvcrt
        last_data = last_status = time.monotonic()
        previous_preview = None
        with (folder/'stream.jsonl').open('w',encoding='utf-8') as log:
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key == '\x03': raise KeyboardInterrupt
                    if key.lower() == 'r':
                        detector.reset()
                        previous_preview = None
                        with stream.condition: cursor = stream.serial
                        log.write(json.dumps({'event':'manual_reset','cursor':cursor})+'\n')
                        print('DA XOA. Lam chuoi moi.',flush=True)
                cursor,batch = stream.read_since(cursor, timeout=.1)
                if not batch and time.monotonic()-last_data > .5:
                    raise ValueError('Du lieu ngung hon 0.5 giay; khong noi mau cu vao chuoi moi')
                if batch: last_data = time.monotonic()
                for row in batch:
                    event = detector.push(row)
                    log.write(json.dumps({'row':row,'prediction':event})+'\n')
                    if event and event.get('state') == 'START':
                        print('DANG NHAN LUOT: tiep tuc cac tu, ve tu the nghi khi xong.',flush=True)
                    if event and event.get('state') == 'RESULT':
                        print('KET QUA LUOT (THU NGHIEM): '+' '.join(w.replace('_',' ') for w in event['tokens']),flush=True)
                        print('SAN SANG CHO LUOT TIEP.',flush=True)
                    if event and event.get('state') == 'UNCERTAIN':
                        reason = 'qua 8 giay; hay ve tu the nghi' if event['reason']=='turn_over_8_seconds' else 'model chua nhan ro; khong tu chen chu'
                        print('CHUA NHAN DUOC: '+reason,flush=True)
                    if event and event.get('state') == 'READY':
                        print('SAN SANG CHO LUOT TIEP.',flush=True)
                    if event and 'preview' in event and event['preview'] != previous_preview:
                        previous_preview = list(event['preview'])
                        text = ' '.join(w.replace('_',' ') for w in previous_preview) or '(chua nhan duoc tu)'
                        print('CUA SO 3 GIAY: '+text,flush=True)
                    if event and event.get('emitted'):
                        print('TU: '+event['emitted'].replace('_',' '),flush=True)
                        print('CHUOI TAM: '+' '.join(w.replace('_',' ') for w in detector.words),flush=True)
                if time.monotonic()-last_status > 3:
                    if args.preview:
                        print('CHAN DOAN | cua so gan nhat, chua chot cau',flush=True)
                    else:
                        print('TRANG THAI: '+{'REST':'SAN SANG','ACTIVE':'DANG NHAN LUOT','WAIT_REST':'CHO VE TU THE NGHI'}[detector.state],flush=True)
                    last_status = time.monotonic()
                log.flush()
    except (KeyboardInterrupt, EOFError):
        print('Da dung.')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f'DUNG: {error}',flush=True)
        return 1
    finally:
        if stream: stream.close()
        elif sock: sock.close()


if __name__ == '__main__':
    raise SystemExit(main())
