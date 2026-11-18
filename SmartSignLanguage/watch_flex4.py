"""Read only F4's display from the existing RAW5_100 firmware."""
import argparse
import time
from .serial_transport import SerialTransport
from .collect_v2 import SampleStream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    args = parser.parse_args()
    stream = sock = None
    try:
        print(f'Ket noi {args.serial_port}; chi hien F4 / AP UT / GPIO35. Ctrl+C: dung.', flush=True)
        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10)
        cursor = 0
        values, steps = [], []
        previous = None
        started = time.monotonic()
        while True:
            cursor, batch = stream.read_since(cursor, timeout=.2)
            for row in batch:
                value = float(row['flex_4'])
                values.append(value)
                if previous is not None:
                    steps.append(abs(value-previous))
                previous = value
            if time.monotonic()-started >= 1 and values:
                print(f'F4={values[-1]:.0f} | TB={sum(values)/len(values):.1f} | '
                      f'min/max={min(values):.0f}/{max(values):.0f} | '
                      f'nhay_max={max(steps, default=0):.0f} | '
                      f'nhay>400={sum(v>400 for v in steps)} | '
                      f'sat_bien={sum(v<=8 or v>=4087 for v in values)}/{len(values)}', flush=True)
                values, steps = [], []
                started = time.monotonic()
    except KeyboardInterrupt:
        print('\nDa dung theo doi F4.')
    except (OSError, ValueError) as error:
        print(f'LOI: {error}', flush=True)
        return 1
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
