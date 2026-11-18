"""Join stable SVM word predictions without requiring rest between different words."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
from .sequence_model_5 import SequenceModel
from .predict_continuous_5 import SlidingRecognizer
from .collect_sequence_5 import calibrate
from .collect_v2 import SampleStream
from .serial_transport import SerialTransport
from .word_sequence_join import StableWordSequence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    parser.add_argument('--model', type=Path, default=Path(__file__).resolve().parent/'models/sequence_5_100hz_U4_20261111_session_eval')
    args = parser.parse_args()
    stream = sock = None
    try:
        model = SequenceModel(args.model)
        joiner = StableWordSequence(model.manifest['labels'])
        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock,flex_count=5,sample_ms=10)
        stream.check_ready()
        reference = calibrate(stream)
        if reference is None:return 0
        detector = SlidingRecognizer(model,reference,confirmations=1)
        folder = Path(__file__).resolve().parents[1]/'.runtime/svm_join'/(
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        (folder/'reference.json').write_text(json.dumps(reference,indent=2),encoding='utf-8')
        (folder/'model.json').write_text(json.dumps({'path':str(args.model.resolve()),
            'sha256':hashlib.sha256((args.model/'model.joblib').read_bytes()).hexdigest(),
            'stable_ms':joiner.stable_ms,'none_ms':joiner.none_ms,
            'method':'timestamped_stability_not_gesture_segmentation'},indent=2),encoding='utf-8')
        print('GHEP TU SVM: '+', '.join(model.manifest['labels']),flush=True)
        print('Lam cac tu nhu luc thu. Khong can ve tu the nghi giua hai tu KHAC NHAU.',flush=True)
        print('Chi CHUOI TU la ket qua da them; DANG XET chua duoc them vao chuoi.',flush=True)
        print('Can nhan cung nhan lien tuc >=1 giay (5 lan). Tu qua nhanh co the bi bo sot.',flush=True)
        print('NONE on dinh 1.5 giay: ket thuc chuoi. Lap cung tu lien tiep can khoang NONE.',flush=True)
        print('R: xoa chuoi. Ctrl+C: dung. Model van co the nham neu nhan sai keo dai.',flush=True)
        print(f'LOG: {folder}',flush=True)
        import msvcrt
        with stream.condition:cursor=stream.serial
        last_data=last_status=time.monotonic()
        stalled=False
        pending_announced=False
        with (folder/'stream.jsonl').open('w',encoding='utf-8') as log:
            while True:
                if msvcrt.kbhit():
                    key=msvcrt.getwch()
                    if key=='\x03':raise KeyboardInterrupt
                    if key.lower()=='r':
                        detector.clear();joiner.reset()
                        pending_announced=False
                        with stream.condition:cursor=stream.serial
                        log.write(json.dumps({'event':'manual_reset','cursor':cursor})+'\n')
                        print('DA XOA CHUOI.',flush=True)
                cursor,batch=stream.read_since(cursor,timeout=.1)
                if not batch:
                    if time.monotonic()-last_data > .5 and not stalled:
                        detector.clear();joiner.reset();stalled=True
                        pending_announced=False
                        print('MAT DU LIEU: ngat chuoi; cho mau moi.',flush=True)
                    if time.monotonic()-last_data > 3:raise ValueError('Khong co du lieu moi trong 3 giay')
                    continue
                last_data=time.monotonic()
                if stalled:
                    stalled=False
                    continue
                for row in batch:
                    # Feed samples individually so prediction cadence does not
                    # depend on USB batch boundaries; detect gaps before joining.
                    previous=detector.last_stamp
                    if previous is not None and not 0 < row['timestamp']-previous <=20:
                        joiner.reset()
                        pending_announced=False
                        print('GIAN DOAN MAU: ngat chuoi cu.',flush=True)
                    prediction=detector.update([row])
                    event=None
                    if prediction:
                        if prediction['state']=='RESULT':
                            event=joiner.update(prediction['label'],prediction['timestamp'])
                        else:
                            joiner.reset()
                            pending_announced=False
                            print('CHO DU LIEU HOP LE: '+prediction['reason'],flush=True)
                    log.write(json.dumps({'row':row,'prediction':prediction,'join':event})+'\n')
                    if event:
                        if event['state']=='PENDING':
                            if not pending_announced:
                                print('DANG XET DONG TAC MOI (chua them tu).',flush=True)
                                pending_announced=True
                        elif event['state']=='WORD':
                            pending_announced=False
                            print('THEM TU: '+event['label'].replace('_',' '),flush=True)
                            print('CHUOI TU: '+' '.join(w.replace('_',' ') for w in event['words']),flush=True)
                        elif event['state']=='FINAL':
                            pending_announced=False
                            print('KET THUC CHUOI: '+' '.join(w.replace('_',' ') for w in event['words']),flush=True)
                log.flush()
                if time.monotonic()-last_status>5:
                    print('DANG CHAY | CHUOI TU: '+(' '.join(w.replace('_',' ') for w in joiner.words) or '(chua co)'),flush=True)
                    last_status=time.monotonic()
    except (KeyboardInterrupt,EOFError):
        print('Da dung.');return 0
    except (ValueError,OSError,KeyError) as error:
        print(f'DUNG: {error}',flush=True);return 1
    finally:
        if stream:stream.close()
        elif sock:sock.close()


if __name__=='__main__':raise SystemExit(main())
