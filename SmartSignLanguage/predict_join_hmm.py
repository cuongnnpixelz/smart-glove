"""Experimental online word-loop decoder; no fixed phrase grammar."""
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
from .sequence_hmm import OnlineWordHMM,WordHMM
from .train_word_ctc import features
from .sequence_model_5 import FLEX_COLUMNS,FLEX_PINS
from .collect_sequence_5 import calibrate
from .collect_v2 import SampleStream
from .serial_transport import SerialTransport


class SensorFrames:
    def __init__(self,reference):
        self.reference=reference;self.reset()

    def reset(self):
        self.rows=deque(maxlen=12);self.count=0;self.last_stamp=None

    def push(self,row):
        stamp=row['timestamp']
        if self.last_stamp is not None and not 0 < stamp-self.last_stamp <=20:
            self.reset();raise ValueError('Mat mau/timestamp: huy doan dang xet')
        for key,pin in zip(FLEX_COLUMNS,FLEX_PINS):
            value=row[key]
            if not np.isfinite(value) or value<=8 or value>=4087:
                self.reset();raise ValueError(f'{key}, GPIO {pin}: ADC={value}; khong dung mau nay de doan')
        self.last_stamp=stamp;self.rows.append(row);self.count+=1
        if self.count%4:return None
        return features(list(self.rows),self.reference)[-1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial-port',default='COM3')
    p.add_argument('--model',type=Path,default=Path(__file__).resolve().parent/'models/word_hmm_u4_phrases_full_v1')
    args=p.parse_args();stream=sock=None
    try:
        manifest=json.loads((args.model/'manifest.json').read_text())
        path=args.model/'model.joblib'
        if manifest.get('schema')!='word-loop-hmm-five-flex-v1' or hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['model_sha256']:
            raise ValueError('Model/manifest khong khop')
        model=joblib.load(path)
        if not isinstance(model,WordHMM) or model.labels!=manifest['labels']:raise ValueError('Sai model')
        decoder=OnlineWordHMM(model)
        sock=SerialTransport(args.serial_port);stream=SampleStream(sock,flex_count=5,sample_ms=10)
        stream.check_ready();reference=calibrate(stream)
        if reference is None:return 0
        frame_builder=SensorFrames(reference)
        folder=Path(__file__).resolve().parents[1]/'.runtime/hmm_join'/(
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        (folder/'reference.json').write_text(json.dumps(reference,indent=2),encoding='utf-8')
        (folder/'model.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print('NHAN CHUOI HMM THU NGHIEM: '+', '.join(model.labels),flush=True)
        print('Lam lien tuc cac tu; khong cho nhan on dinh 1 giay, khong can nghi giua tung tu.',flush=True)
        print('Chi them tu khi cac duong giai ma dong y ve tu da ket thuc. Co the cham/bo sot/nham.',flush=True)
        print('R: xoa; ENTER: chot cac tu da nhan; Ctrl+C: dung. Nen duoc nhan on dinh se tu chot.',flush=True)
        print(f'LOG: {folder}',flush=True)
        import msvcrt
        with stream.condition:cursor=stream.serial
        words=[];rest_since=None;bad=False;stalled=False;last_data=last_status=time.monotonic()
        with (folder/'stream.jsonl').open('w',encoding='utf-8') as log:
            while True:
                if msvcrt.kbhit():
                    key=msvcrt.getwch()
                    if key=='\x03':raise KeyboardInterrupt
                    if key.lower()=='r' or key=='\r':
                        if key=='\r':print('CHUOI DA NHAN: '+' '.join(w.replace('_',' ') for w in words),flush=True)
                        log.write(json.dumps({'event':'manual_finish' if key=='\r' else 'manual_reset','words':words})+'\n')
                        words=[];decoder.reset();frame_builder.reset();rest_since=None
                        with stream.condition:cursor=stream.serial
                cursor,batch=stream.read_since(cursor,timeout=.1)
                if not batch:
                    if time.monotonic()-last_data>3:raise ValueError('Khong nhan du lieu trong 3 giay')
                    if time.monotonic()-last_data>.5 and not stalled:
                        decoder.reset();frame_builder.reset();rest_since=None
                        log.write(json.dumps({'event':'data_stall','partial_words':words})+'\n');log.flush()
                        words=[];stalled=True
                        print('MAT DU LIEU: ngat chuoi, cho mau moi.',flush=True)
                    continue
                last_data=time.monotonic()
                if stalled:
                    stalled=False
                    continue
                for row in batch:
                    event=None;error=None
                    try:
                        frame=frame_builder.push(row)
                        if frame is not None:event=decoder.push(frame,row['timestamp'])
                    except ValueError as exc:
                        error=str(exc);decoder.reset();frame_builder.reset();rest_since=None
                        if not bad:
                            print('DU LIEU LOI: '+error,flush=True)
                            if words:print('CHUOI TRUOC GIAN DOAN: '+' '.join(words),flush=True)
                        bad=True;words=[]
                    log.write(json.dumps({'row':row,'prediction':event,'error':error})+'\n')
                    if event:
                        if bad:print('DA CO MAU HOP LE TRO LAI.',flush=True);bad=False
                        if event['words']:
                            words.extend(event['words'])
                            print('CHUOI TU: '+' '.join(w.replace('_',' ') for w in words),flush=True)
                        if event['background_best'] and not event['pending_best']:
                            if rest_since is None:rest_since=row['timestamp']
                            if words and row['timestamp']-rest_since>=1500:
                                print('KET THUC CHUOI: '+' '.join(w.replace('_',' ') for w in words),flush=True)
                                log.write(json.dumps({'event':'auto_finish','words':words})+'\n')
                                words=[];decoder.reset();frame_builder.reset();rest_since=None
                        else:rest_since=None
                log.flush()
                if time.monotonic()-last_status>5:
                    print('DANG NHAN | '+(' '.join(w.replace('_',' ') for w in words) or 'chua co tu du dieu kien'),flush=True)
                    last_status=time.monotonic()
    except (KeyboardInterrupt,EOFError):print('Da dung.');return 0
    except (OSError,ValueError,KeyError) as error:print(f'DUNG: {error}',flush=True);return 1
    finally:
        if stream:stream.close()
        elif sock:sock.close()


if __name__=='__main__':raise SystemExit(main())
