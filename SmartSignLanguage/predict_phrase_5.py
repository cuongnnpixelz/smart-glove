"""Experimental continuous whole-phrase recognition, separate from word models."""
import argparse
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import time
import numpy as np

if __package__:
    from .phrase_model import PhraseModel, MODEL_PREFIX
    from .five_finger import check_imu_range
    from .phrase_data import make_phrase_reference
    from .collect_sequence_5 import calibrate
    from .collect_v2 import SampleStream
    from .serial_transport import SerialTransport
    from .predict_continuous_5 import initialize_imu, send_state, send_result
else:
    from phrase_model import PhraseModel, MODEL_PREFIX
    from five_finger import check_imu_range
    from phrase_data import make_phrase_reference
    from collect_sequence_5 import calibrate
    from collect_v2 import SampleStream
    from serial_transport import SerialTransport
    from predict_continuous_5 import initialize_imu, send_state, send_result

BASE=Path(__file__).resolve().parent


class PhraseDetector:
    """Arm at rest, then capture a whole timed episode before any prediction.

    Motion thresholds are conservative starting settings, not learned confidence.
    A completed timed episode can still be misclassified by the model.
    """
    def __init__(self, model, reference):
        self.model = model
        self.reference = reference
        self.duration_ms = round(max(model.durations)*1000)
        self.size = round(max(model.durations)*100)
        self.last = None
        self.bias = np.asarray(reference['gyro_bias'])
        self.flex_keys = [f'flex_{i}' for i in range(1, 6)]
        self.spans = np.asarray([abs(reference['flex_calibration'][k]['open']-
                                     reference['flex_calibration'][k]['closed']) for k in self.flex_keys])
        self.reset()

    def reset(self):
        self.rows = []
        self.rest = deque(maxlen=70)
        self.recent = deque(maxlen=5)
        self.state = 'REST'
        self.onset = []
        self.started = None
        self.progress_bucket = -1

    def _signals(self, row):
        flex = np.asarray([row[k] for k in self.flex_keys], dtype=float)
        acc = np.asarray([row[k] for k in ('ACCx', 'ACCy', 'ACCz')], dtype=float)
        gyro = np.asarray([row[k] for k in ('GYRx', 'GYRy', 'GYRz')], dtype=float)
        if not np.isfinite(np.r_[flex, acc, gyro]).all():
            raise ValueError('Du lieu cam bien khong huu han')
        if np.any((flex <= 8) | (flex >= 4087)):
            names = ('CAI', 'TRO', 'GIUA', 'AP UT', 'UT')
            pins = (32, 33, 34, 35, 36)
            faults = [f'F{i+1} ({names[i]}, GPIO {pins[i]}): ADC={value:g} '
                      f"({'gan 0' if value <= 8 else 'gan 4095'})"
                      for i, value in enumerate(flex) if value <= 8 or value >= 4087]
            raise ValueError('Flex sat bien: ' + '; '.join(faults) +
                             '. BO luot; kiem tra day/cam bien cac ngon tren.')
        check_imu_range(np.r_[flex, acc, gyro][None, :], self.reference)
        return flex, acc, float(np.linalg.norm(gyro-self.bias))

    def _finish(self):
        rows = self.rows
        try:
            if callable(getattr(type(self.model), 'predict_episode', None)):
                return self.model.predict_episode(rows, self.reference)
            candidates = {self.model.predict(rows[:round(seconds*100)], self.reference)
                          for seconds in self.model.durations}
            positives = candidates-{'NONE'}
            if len(positives) == 1:
                return {'state': 'RESULT', 'label': positives.pop()}
            if not positives:
                return {'state': 'NONE'}
            return {'state': 'WAIT', 'reason': 'Chua nhan ro cau; nghi tay roi thu lai'}
        except ValueError as error:
            return {'state': 'ERROR', 'reason': str(error)}
        finally:
            self.reset()

    def _step(self, row):
        stamp = row['timestamp']
        flex, acc, speed = self._signals(row)
        self.recent.append((flex, acc, speed))
        if self.state == 'CAPTURE':
            self.rows.append(row)
            elapsed = stamp-self.started
            # Wait at least the entire configured duration after detected onset.
            # Never fill the front of this window with old resting samples.
            if elapsed >= self.duration_ms and len(self.rows) >= self.size:
                return self._finish()
            bucket = int(elapsed//500)
            if bucket != self.progress_bucket:
                self.progress_bucket = bucket
                return {'state': 'WAIT', 'reason': f'DANG THU CAU: {elapsed/1000:.1f}/{self.duration_ms/1000:g}s - tiep tuc thuc hien'}
            return None
        if self.state == 'REST':
            self.rest.append((flex, acc, speed))
            if len(self.rest) < 70:
                return None
            values = list(self.rest)
            f = np.asarray([v[0] for v in values])
            a = np.asarray([v[1] for v in values])
            quiet = (np.percentile([v[2] for v in values], 90) < .2
                     and np.max(np.abs(np.median(f[:35],axis=0)-np.median(f[35:],axis=0))/self.spans) < .08
                     and np.linalg.norm(np.median(a[:35],axis=0)-np.median(a[35:],axis=0)) < .3)
            if quiet:
                self.baseline_flex = np.median(f,axis=0)
                self.baseline_acc = np.median(a,axis=0)
                self.state = 'ARMED'
                return {'state': 'WAIT', 'reason': 'SAN SANG - bat dau cau bang chuyen dong ro rang; cu dong nhe se duoc bo qua'}
            return None
        filtered_flex = np.median([v[0] for v in self.recent],axis=0)
        filtered_acc = np.median([v[1] for v in self.recent],axis=0)
        # Stronger onset only; once captured, retain even gentle phrase motion.
        # Require sustained evidence, not a single jerk. Keep all confirming
        # samples so the 200 ms confirmation does not shift the model window.
        moving = (speed > .75
                  or np.max(np.abs(filtered_flex-self.baseline_flex)/self.spans) > .35
                  or np.linalg.norm(filtered_acc-self.baseline_acc) > 3.0)
        if not moving:
            self.onset.clear()
            return None
        self.onset.append(row)
        if stamp - self.onset[0]['timestamp'] >= 200:
            self.started = self.onset[0]['timestamp']
            self.rows = list(self.onset)
            self.state = 'CAPTURE'
            self.progress_bucket = 0
            return {'state': 'WAIT', 'reason': f'BAT DAU - DANG THU CAU: {(stamp-self.started)/1000:.1f}/{self.duration_ms/1000:g}s - tiep tuc lam tron cau'}
        return None

    def update(self, batch):
        event = None
        for row in batch:
            stamp = row['timestamp']
            if self.last is not None:
                if stamp <= self.last:
                    self.reset()
                    raise ValueError('ESP32 reset/timestamp quay nguoc')
                if stamp-self.last > 20:
                    self.reset()
                    event = {'state': 'WAIT', 'reason': 'Mat mau; bo luot, giu tay nghi de bat dau lai'}
            self.last = stamp
            try:
                new_event = self._step(row)
            except ValueError as error:
                self.reset()
                new_event = {'state': 'ERROR', 'reason': str(error)}
            if new_event and (not event or event['state'] not in ('RESULT', 'ERROR', 'NONE')):
                event = new_event
        return event


def latest_model():
    paths=[p.parent for p in (BASE/'models').glob(MODEL_PREFIX+'*/manifest.json') if (p.parent/'model.joblib').exists()]
    if not paths:
        raise ValueError('Chua co model cau; chay train_phrase_5.py')
    return max(paths,key=lambda p:(p/'manifest.json').stat().st_mtime_ns)


def recognize_live(stream, model, reference, run_seconds=None):
    detector=PhraseDetector(model,reference)
    detector.duration_ms=max(5000,detector.duration_ms)
    with stream.condition:cursor=stream.serial
    send_state(stream.sock,'WAIT')
    print('GIU TAY NGHI it nhat 0.7s. Khi SAN SANG, dua tay len lam cau nhu luc thu; chi du doan sau khi thu du thoi gian.',flush=True)
    print('Chi BAT DAU khi chuyen dong ro lien tuc 0.2s. Khong can giat manh; khi da thu, cu dong nhe van duoc ghi.',flush=True)
    print('Nhan dien lien tuc thu nghiem; khong bam Enter tung cau. Ctrl+C de dung. Chua bat doc am thanh.',flush=True)
    started=last_data=time.monotonic()
    last_message=None
    rest_until=None
    rest_count=None
    while run_seconds is None or time.monotonic()-started<run_seconds:
        cursor,batch=stream.read_since(cursor,.25)
        if not batch:
            if time.monotonic()-last_data>.5:
                detector.reset();send_state(stream.sock,'WAIT')
            if time.monotonic()-last_data>3:raise ValueError('Mat du lieu 3 giay')
            continue
        last_data=time.monotonic()
        if rest_until is not None:
            remaining=rest_until-time.monotonic()
            if remaining>0:
                count=int(np.ceil(remaining))
                if count!=rest_count:
                    print(f'NGHI {count}s - dua tay ve tu the ban dau. KHONG NHAN DONG TAC.',flush=True)
                    rest_count=count
                continue
            # Discard return-to-rest motion and all samples buffered during the break.
            detector.reset()
            detector.last=None
            rest_until=None
            rest_count=None
            send_state(stream.sock,'WAIT')
            print('\nCHO SAN SANG - giu tay nghi yen it nhat 0.7s.',flush=True)
            last_message=None
            continue
        event=detector.update(batch)
        if event is None:continue
        completed=event['state'] in ('RESULT','NONE') or (
            detector.state=='REST' and event['state'] in ('WAIT','ERROR'))
        if event['state']=='RESULT':
            send_result(stream.sock,event['label'])
            print('\n'+'='*50+'\nKET QUA: '+event['label'].replace('_',' ')+'\n'+'='*50,flush=True)
            last_message=None
        else:
            send_state(stream.sock,'ERROR' if event['state']=='ERROR' else 'WAIT')
            message='NONE - dang nghi/ngoai cac cau' if event['state']=='NONE' else event['reason']
            if message!=last_message:print(message,flush=True);last_message=message
        if completed:
            detector.reset()
            rest_until=time.monotonic()+3
            rest_count=3
            print('NGHI 3s - dua tay ve tu the ban dau. KHONG NHAN DONG TAC.',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port',default='COM3')
    parser.add_argument('--user-id',default='U02')
    parser.add_argument('--model',type=Path)
    parser.add_argument('--recalibrate',action='store_true')
    parser.add_argument('--combine-words',action='store_true',help='Experimental word/phrase arbitration with conflict rejection')
    parser.add_argument('--check-connection',action='store_true',help='Read 3 seconds of raw data then close; no recognition')
    parser.add_argument('--run-seconds',type=float,help='Optional bounded live run after calibration')
    args=parser.parse_args(argv)
    stream=sock=None
    try:
        folder=args.model or latest_model()
        model=PhraseModel(folder)
        if args.combine_words:
            if __package__:
                from .combined_recognition import CombinedModel
            else:
                from combined_recognition import CombinedModel
            model=CombinedModel(model,BASE/'models')
        print(f'MODEL CAU: {folder}',flush=True)
        print('NHAN: '+', '.join(model.manifest['labels']))
        print('THOI GIAN: '+', '.join(str(s)+'s' for s in model.durations))
        sock=SerialTransport(args.serial_port)
        stream=SampleStream(sock,flex_count=5,sample_ms=10)
        stream.check_ready()
        if args.check_connection:
            rows=stream.capture(3)
            print(f'KET NOI DAT: {len(rows)} mau raw trong 3 giay; MPU {stream.imu_ranges}. Chua danh gia nhan dien.')
            return 0
        if args.recalibrate:
            reference=calibrate(stream)
            if reference is None:return 0
        else:
            refs=[]
            for path in (BASE/'phrase_data_5_100hz').rglob('imu_reference.json'):
                if not list(path.parent.glob('*.csv')):continue
                ref=json.loads(path.read_text(encoding='utf-8'))
                if ref.get('user_id')==args.user_id:refs.append(path)
            if not refs:raise ValueError('Khong co moc cho nguoi nay; dung --recalibrate')
            path=max(refs,key=lambda p:p.stat().st_mtime_ns)
            saved=deepcopy(json.loads(path.read_text(encoding='utf-8')))
            saved.update(trial_seconds=1.5,sample_count=150)
            print(f'MOC FLEX: {path}')
            reference=initialize_imu(stream,saved)
        reference=make_phrase_reference(reference)
        reconnects = 0
        deadline = None if args.run_seconds is None else time.monotonic()+args.run_seconds
        while True:
            try:
                if stream is None:
                    sock=SerialTransport(args.serial_port)
                    stream=SampleStream(sock,flex_count=5,sample_ms=10)
                    stream.check_ready()
                    physical=deepcopy(reference)
                    physical.update(trial_seconds=1.5,sample_count=150)
                    reference=make_phrase_reference(initialize_imu(stream,physical))
                    print('DA NOI LAI - giu nguyen moc flex; bo luot cu, cho SAN SANG de lam lai cau.',flush=True)
                remaining=None if deadline is None else max(0,deadline-time.monotonic())
                recognize_live(stream,model,reference,remaining)
                break
            except (OSError,ValueError) as error:
                print(f'TAM DUNG: {error}. BO luot dang lam, khong du doan tu du lieu hong.',flush=True)
                if stream:
                    try:send_state(stream.sock,'ERROR')
                    except OSError:pass
                    stream.close()
                elif sock:
                    sock.close()
                stream=sock=None
                if reconnects>=3:
                    raise ValueError('Ket noi loi lap lai sau 3 lan phuc hoi. Kiem tra cap USB, cong USB va nguon; khong tiep tuc doan.') from error
                if deadline is not None and time.monotonic()>=deadline:
                    raise
                reconnects+=1
                print(f'Tu noi lai {reconnects}/3 sau 2 giay. GIU TAY YEN de khoi tao MPU; Ctrl+C de dung.',flush=True)
                time.sleep(2)
        return 0
    except (OSError,ValueError,KeyError,ImportError) as error:
        print(f'LOI: {error}',flush=True)
        return 1
    except (KeyboardInterrupt,EOFError):
        print('\nDa dung nhan dien cau.')
        return 0
    finally:
        if stream:
            try:send_state(sock,'OFF')
            except OSError:pass
            stream.close()
        elif sock:sock.close()


if __name__=='__main__':raise SystemExit(main())
