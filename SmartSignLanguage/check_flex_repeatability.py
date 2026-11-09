"""Guided raw sensor measurements; never adds samples to the training dataset."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import uuid

import numpy as np

if __package__:
    from .collect_v2 import SampleStream
    from .serial_transport import SerialTransport
else:
    from collect_v2 import SampleStream
    from serial_transport import SerialTransport

KEYS = [f'flex_{i}' for i in range(1, 6)]


def summarize(rows):
    result = {}
    for key in KEYS:
        values = np.array([r[key] for r in rows], dtype=float)
        result[key] = {'median': float(np.median(values)),
                       'p90_width': float(np.percentile(values, 95)-np.percentile(values, 5)),
                       'min': float(values.min()), 'max': float(values.max()),
                       'rail_samples': int(np.sum((values <= 8) | (values >= 4087)))}
    return result


def comparison(first, second):
    return {key: {'shift_adc': second[key]['median']-first[key]['median'],
                  'first_p90_width': first[key]['p90_width'],
                  'second_p90_width': second[key]['p90_width']}
            for key in KEYS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    args = parser.parse_args(argv)
    folder = Path(__file__).resolve().parents[1]/'.runtime'/'flex_checks'/(
        datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    stream = None
    sock = None
    report = {'status': 'incomplete', 'port': args.serial_port, 'poses': {}, 'comparisons': {}}
    try:
        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10)
        stream.check_ready()
        folder.mkdir(parents=True)
        print('KIEM TRA FLEX: khong train, khong doi hieu chuan. Giu co tay cung huong moi lan.')
        print('Moi tu the: ENTER de do 5 giay, Q de dung. Chuong trinh tu luu so do.')
        steps = [('OPEN_1', 'DUOI ca 5 ngon thoai mai'),
                 ('OPEN_2', 'Nam/duoi nhe 10 lan, sau do DUOI ca 5 ngon'),
                 ('B_1', 'Tao chu B'), ('C_1', 'Tao chu C'), ('D_1', 'Tao chu D'),
                 ('B_2', 'Tao lai chu B'), ('C_2', 'Tao lai chu C'), ('D_2', 'Tao lai chu D'),
                 ('OPEN_3', 'DUOI ca 5 ngon lan cuoi')]
        for name, instruction in steps:
            if input(f'\n{instruction}. ENTER: do | Q: dung > ').strip().upper() == 'Q':
                return 0
            while True:
                print('DANG DO - GIU YEN 5 GIAY...', flush=True)
                try:
                    raw = stream.capture(5)
                    break
                except ValueError as error:
                    if stream.error:
                        raise
                    print(f'Luot chua dat: {error}')
                    if input('ENTER: thu lai | Q: dung > ').strip().upper() == 'Q':
                        return 0
            # Save the full capture to inspect recovery over time, but summarize
            # the last two seconds after settling rather than hand transitions.
            stable = [r for r in raw if r['timestamp'] >= raw[-1]['timestamp']-2000]
            stats = summarize(stable)
            report['poses'][name] = {'summary': stats, 'raw': raw}
            print('DA DO ' + name + '. ' + ('CAN KIEM TRA DAY: co ADC sat bien.' if
                  any(s['rail_samples'] for s in stats.values()) else 'Da luu, chuyen buoc tiep.'))
            (folder/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        for first, second in [('OPEN_1', 'OPEN_2'), ('OPEN_1', 'OPEN_3'),
                              ('B_1', 'B_2'), ('C_1', 'C_2'), ('D_1', 'D_2')]:
            delta = comparison(report['poses'][first]['summary'], report['poses'][second]['summary'])
            report['comparisons'][first+'__'+second] = delta
            print(first+' -> '+second+': '+ ' | '.join(
                f'F{i+1} lech {delta[key]["shift_adc"]:+.1f} ADC' for i, key in enumerate(KEYS)))
        report['status'] = 'complete'
        print('DA XONG. So lech chua tu ket luan cam bien hong; can doi chieu bien do va du lieu train.')
        return 0
    except (OSError, ValueError, ImportError) as error:
        report['error'] = str(error)
        print(f'LOI: {error}')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nDa dung; cac buoc da do van duoc luu.')
        return 0
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()
        if folder.exists():
            (folder/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(f'BAO CAO: {folder / "report.json"}')


if __name__ == '__main__':
    raise SystemExit(main())
