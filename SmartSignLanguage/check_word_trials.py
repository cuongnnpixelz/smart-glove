"""Interactive, isolated word evaluation; logs are never training data."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid

if __package__:
    from .collect_sequence_5 import calibrate, countdown
    from .collect_v2 import SampleStream
    from .serial_transport import SerialTransport
    from .sequence_model_5 import SequenceModel
    from .five_finger import trial_quality
else:
    from collect_sequence_5 import calibrate, countdown
    from collect_v2 import SampleStream
    from serial_transport import SerialTransport
    from sequence_model_5 import SequenceModel
    from five_finger import trial_quality


def evaluate_trial(stream, model, reference):
    stream.check_ready()
    countdown()
    try:
        cursor = stream.start_trial()
        print('BAT DAU - lam MOT tu trong 1.5 giay; xong giu tu the cuoi.', flush=True)
        rows = stream.capture(1.5, sample_count=150, after=cursor)
    finally:
        stream.sock.sendall(b'STOP\n')
    trial_quality(rows, reference)
    # Expected label is intentionally not passed to the classifier.
    return model.predict(rows, reference), rows


def run_trials(stream, model, reference, folder):
    labels = model.manifest['labels']
    total = correct = attempt = 0
    print('NHAN: ' + ', '.join(labels), flush=True)
    print('Nhap tu BAN SE LAM truoc moi luot. NONE: nghi/chuyen dong nen. Q: dung.', flush=True)
    try:
        while True:
            expected = input('Tu se lam > ').strip().upper().replace(' ', '_')
            if expected in ('Q', '/Q'):
                return
            if expected not in labels:
                print('Hay nhap mot nhan trong danh sach.')
                continue
            attempt += 1
            predicted, rows = evaluate_trial(stream, model, reference)
            print('HET THU. MAY DOAN: ' + predicted, flush=True)
            while True:
                review = input('ENTER: da lam dung dong tac | R: toi lam hong, loai luot | Q: loai va dung > ').strip().upper()
                if review in ('', 'R', 'Q'):
                    break
            valid = review == ''
            record = {'expected': expected, 'predicted': predicted, 'performed_as_intended': valid,
                      'rows': rows, 'sample_count': len(rows)}
            (folder/f'trial_{attempt:03d}.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            if valid:
                total += 1
                correct += int(expected == predicted)
                print(f"{'DUNG' if expected == predicted else 'SAI'} | {correct}/{total} luot hop le", flush=True)
            if review == 'Q':
                return
    finally:
        (folder/'summary.json').write_text(json.dumps({'correct': correct, 'total': total,
            'accuracy': correct/total if total else None, 'attempts': attempt}, indent=2), encoding='utf-8')
        print(f'KET QUA: {correct}/{total}. Log: {folder.resolve()}', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args(argv)
    stream = sock = None
    try:
        model = SequenceModel(args.model)
        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10)
        stream.check_ready()
        reference = calibrate(stream)
        if reference is None:
            return 0
        sid = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
        folder = Path(__file__).resolve().parents[1]/'.runtime'/'word_checks'/sid
        folder.mkdir(parents=True, exist_ok=False)
        (folder/'reference.json').write_text(json.dumps(reference, indent=2), encoding='utf-8')
        (folder/'model.json').write_text(json.dumps({'path': str(args.model.resolve()),
            'manifest': model.manifest}, indent=2), encoding='utf-8')
        run_trials(stream, model, reference, folder)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Da dung.')
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f'DUNG KIEM TRA: {error}. Khong du doan tu du lieu loi.')
        return 1
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()


if __name__ == '__main__':
    raise SystemExit(main())
