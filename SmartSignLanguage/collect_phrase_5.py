"""Collect named whole phrases over USB with a user-selected duration per label."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from copy import deepcopy

if __package__:
    from .collect_sequence_5 import calibrate, countdown, normalize_word, prompt, recover_imu
    from .collect_sequence import save_trial
    from .collect_v2 import SampleStream
    from .serial_transport import SerialTransport
    from .session_folder import folder_name, user_folder
    from .session_csv import label_filename
    from .five_finger import CSV_COLUMNS
    from .predict_continuous_5 import initialize_imu
    from .phrase_data import validate_duration, sample_count, phrase_quality, make_phrase_reference, validate_phrase_reference
else:
    from collect_sequence_5 import calibrate, countdown, normalize_word, prompt, recover_imu
    from collect_sequence import save_trial
    from collect_v2 import SampleStream
    from serial_transport import SerialTransport
    from session_folder import folder_name, user_folder
    from session_csv import label_filename
    from five_finger import CSV_COLUMNS
    from predict_continuous_5 import initialize_imu
    from phrase_data import validate_duration, sample_count, phrase_quality, make_phrase_reference, validate_phrase_reference

BASE = Path(__file__).resolve().parent


def ask_duration(default):
    while True:
        value = input(f'Thoi gian thu (1..10 giay; vd 3, 5, 3.5; ENTER={default:g}s) > ').strip()
        if value.upper() in ('Q', '/Q'):
            return None
        try:
            return validate_duration(value.lower().removesuffix('s').strip().replace(',', '.') if value else default)
        except (TypeError, ValueError) as error:
            print(f'Khong hop le: {error}')


def ask_repetitions(default):
    while True:
        value = input(f'So luot muon thu (ENTER={default}) > ').strip()
        if value.upper() in ('Q', '/Q'):
            return None
        try:
            count = int(value) if value else default
            if count >= 1:
                return count
        except ValueError:
            pass
        print('Nhap so nguyen >= 1.')


def write_reference(folder, reference):
    validate_phrase_reference(reference)
    (folder/'imu_reference.json').write_text(json.dumps(reference, indent=2), encoding='utf-8')


def refresh_saved_flex(stream, saved):
    """Reuse flex endpoints only; remeasure IMU after a connection/reset."""
    physical = deepcopy(saved)
    physical.update(trial_seconds=1.5, sample_count=150)
    return make_phrase_reference(initialize_imu(stream, physical))


def latest_user_reference(args):
    paths = []
    for path in args.output_dir.rglob('imu_reference.json'):
        ref = json.loads(path.read_text(encoding='utf-8'))
        if ref.get('user_id') == args.user_id:
            validate_phrase_reference(ref)
            paths.append((path, ref))
    if not paths:
        raise ValueError('Chua co moc flex cua nguoi nay; chay khong co --reuse-flex')
    path, ref = max(paths, key=lambda item: item[0].stat().st_mtime_ns)
    print(f'DUNG LAI MOC FLEX: {path}')
    return ref


def reconnect_session(args, previous):
    """A reopened COM may reset timestamps: use a new session, not old CSVs."""
    while True:
        print('Kiem tra USB. Chi tiep tuc neu van cung nguoi, chua thao gang/chinh flex.')
        if prompt('ENTER: noi lai, giu moc flex | Q: dung de hieu chuan lai > ') == 'Q':
            return None
        sock = stream = None
        try:
            sock = SerialTransport(args.serial_port)
            stream = SampleStream(sock, flex_count=5, sample_ms=10, recover_collection_gaps=True)
            stream.check_ready()
            reference = refresh_saved_flex(stream, previous)
            sid = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
            folder = args.output_dir/user_folder(args.user_id)/folder_name(sid, args.user_id, ['CAU_TIEP_TUC'])
            reference.update(user_id=args.user_id, session_id=sid,
                             labels=list(previous['labels']), label_settings=deepcopy(previous['label_settings']),
                             resumed_from=previous['session_id'], data_layout='per-label-csv-v1',
                             transport='usb-serial', connection=args.serial_port, serial_baud=230400)
            folder.mkdir(parents=True, exist_ok=False)
            write_reference(folder, reference)
            print(f'DA NOI LAI. Giu luot da luu, thu tiep luot con thieu. Phien tiep: {folder}')
            return stream, sock, reference, folder, sid
        except (OSError, ValueError) as error:
            print(f'CHUA NOI LAI: {error}')
            if stream:
                stream.close()
            elif sock:
                sock.close()
        except BaseException:
            if stream:
                stream.close()
            elif sock:
                sock.close()
            raise


def collect_session(args):
    sid = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    folder = args.output_dir/user_folder(args.user_id)/folder_name(sid, args.user_id, ['CAU_TUY_CHON'])
    sock = stream = None
    try:
        print(f'Ket noi {args.serial_port}, 230400 baud...', flush=True)
        sock = SerialTransport(args.serial_port)
        stream = SampleStream(sock, flex_count=5, sample_ms=10, recover_collection_gaps=True)
        quality = stream.check_ready()
        print(f'Du lieu: {quality["hz"]:.2f} Hz. Hieu chuan 5 ngon mot lan dau phien.')
        if args.reuse_flex:
            print('Chi dung lai moc neu cung nguoi va gang/flex chua thay doi. MPU van can giu yen de khoi tao.')
            reference = refresh_saved_flex(stream, latest_user_reference(args))
        else:
            reference = calibrate(stream)
            if reference is None:
                return 0
            reference = make_phrase_reference(reference)
        reference.update(user_id=args.user_id, session_id=sid, labels=[],
                         data_layout='per-label-csv-v1', transport='usb-serial',
                         connection=args.serial_port, serial_baud=230400)
        folder.mkdir(parents=True, exist_ok=False)
        write_reference(folder, reference)
        print(f'PHIEN THU CAU: {folder}')
        print('Nhap nhan cau tuy y. Vi du: TOI_CAM_ON_BAN. NONE: nghi/chuyen dong ngoai cac cau.')
        print('Moi cau duoc chon thoi gian rieng. Tay nghi luc dem nguoc; BAT DAU moi dua tay len lam tron cau MOT lan.')
        print('Lam xong som: giu tu the cuoi den HET THOI GIAN. Chua xong: R de bo, khong luu cau bi cat.')
        print('Du lieu cau dung model rieng; lenh train/nhan dien chu-tu 1.5s hien tai khong doc bo nay.')
        counts = Counter()
        trial_id = 1
        while True:
            word = 'NONE' if args.none_only else input('\nNhap cau/nhan muon thu | /Q: ket thuc > ').strip()
            if word.upper() == '/Q':
                return 0
            try:
                label = normalize_word(word)
            except ValueError as error:
                print(f'Nhan khong hop le: {error}')
                continue
            settings = reference['label_settings'].get(label)
            if settings is None:
                seconds = args.seconds if args.none_only else ask_duration(args.seconds)
                if seconds is None:
                    return 0
                settings = {'seconds': seconds, 'sample_count': sample_count(seconds), 'display_text': word}
            else:
                seconds = settings['seconds']
                print(f'{label} da chon {seconds:g}s trong phien nay; giu cung thoi gian khi thu them.')
            repetitions = args.repetitions if args.none_only else ask_repetitions(args.repetitions)
            if repetitions is None:
                return 0
            if label not in reference['label_settings']:
                reference['labels'].append(label)
                reference['label_settings'][label] = settings
                write_reference(folder, reference)
            target = counts[label]+repetitions
            print(f'{label}: {seconds:g}s, {settings["sample_count"]} mau/luot. File: {label_filename(label)}')
            if label == 'NONE':
                print('NONE: nghi, chuyen tay hoac chuoi lam do; khong thuc hien tron cau dung.')
            while counts[label] < target:
                if args.none_only:
                    command = prompt(f'[NONE {counts[label]+1}/{target}] ENTER: chuan bi | Q: dung > ', ('', 'Q'))
                else:
                    command = prompt(f'[{label} {counts[label]+1}/{target}] ENTER: chuan bi | M: doi cau | Q: dung > ', ('', 'M', 'Q'))
                if command == 'Q':
                    return 0
                if command == 'M':
                    break
                try:
                    stream.check_ready()
                    countdown()
                    try:
                        cursor = stream.start_trial()
                        print(f'BAT DAU {label} - THU {seconds:g} GIAY', flush=True)
                        rows = stream.capture(seconds, sample_count=settings['sample_count'], after=cursor)
                    finally:
                        stream.sock.sendall(b'STOP\n')
                    quality = phrase_quality(rows, seconds, reference)
                except (ValueError, OSError) as error:
                    if stream.error or isinstance(error, OSError):
                        print(f'MAT DU LIEU: {stream.error or error}. Luot dang thu bi bo; luot da luu van con.')
                        stream.close()
                        stream = sock = None
                        recovered = reconnect_session(args, reference)
                        if recovered is None:
                            return 0
                        stream, sock, reference, folder, sid = recovered
                        trial_id = 1
                        continue
                    print(f'BO LUOT: {error}')
                    if stream.recovery_required and not recover_imu(stream, reference, folder, trial_id):
                        return 0
                    continue
                print(f'HET THOI GIAN: {len(rows)} mau, {quality["hz"]:.2f} Hz. Da lam tron cau chua?', flush=True)
                if args.none_only:
                    review = prompt('ENTER: luu NONE | R: bo va thu lai | Q: bo va dung > ', ('', 'R', 'Q'))
                else:
                    review = prompt('ENTER: luu | R: bo va thu lai | M: bo va doi cau | Q: bo va dung > ', ('', 'R', 'M', 'Q'))
                if review == 'Q':
                    return 0
                if review == 'M':
                    break
                if review == 'R':
                    continue
                save_trial(folder/label_filename(label), rows, args.user_id, sid, trial_id, label,
                           columns=CSV_COLUMNS, quality_check=lambda batch: phrase_quality(batch, seconds, reference))
                counts[label] += 1
                trial_id += 1
                print(f'DA LUU {label}: {counts[label]}/{target} | {seconds:g}s | {len(rows)} mau', flush=True)
            if args.none_only:
                print(f'HOAN TAT: da luu {counts[label]} luot NONE.', flush=True)
                return 0
    except (OSError, ValueError, ImportError) as error:
        print(f'LOI: {error}. Cac luot da luu van con; luot chua hoan tat khong duoc luu.')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nDa dung. Cac luot da luu van con.')
        return 0
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()
        if sock:
            print('Da dong COM; firmware USB + Wi-Fi se noi lai Wi-Fi.')
        if folder.exists():
            print(f'DU LIEU CAU: {folder}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    parser.add_argument('--user-id', default='U02')
    parser.add_argument('--seconds', type=validate_duration, default=3.0, help='Default seconds; also selectable for each phrase')
    parser.add_argument('--repetitions', type=int, default=10)
    parser.add_argument('--none-only', action='store_true', help='Only collect NONE; stop after the requested valid repetitions')
    parser.add_argument('--reuse-flex', action='store_true', help='Reuse latest flex calibration for this user; still reinitialize MPU')
    parser.add_argument('--output-dir', type=Path, default=BASE/'phrase_data_5_100hz')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.user_id) or args.repetitions < 1:
        parser.error('user-id: 1..40 A-Z/a-z/0-9/_/-; repetitions >= 1')
    if args.output_dir.resolve().is_relative_to((BASE/'sequence_data_5_100hz').resolve()):
        parser.error('Hay luu cau trong thu muc rieng, khong tron du lieu chu/tu 1.5s.')
    return collect_session(args)


if __name__ == '__main__':
    raise SystemExit(main())
