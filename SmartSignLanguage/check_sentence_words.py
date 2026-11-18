"""Manually labelled sentence trials: capture, decode, and save observations."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from .collect_sequence_5 import calibrate, countdown
from .collect_v2 import SampleStream
from .predict_continuous_5 import initialize_imu, latest_reference
from .predict_sentence_words import DEFAULT_MODEL, WORD_TEXT, decode_five_seconds, format_sentence
from .none_sentence_capture import capture_until_none
from .predict_sentence_words import filter_window_predictions
from .sequence_model_5 import SequenceModel
from .serial_transport import SerialTransport
from .esp32_speech import ESP32Speaker, add_speech_arguments
from .sentence_check_excel import WORKBOOK, export_workbook, sentence_key


def update_excel():
    while True:
        try:
            return export_workbook()
        except PermissionError:
            input(f'Đóng file Excel {WORKBOOK.name} rồi Enter để cập nhật (log đã được giữ) > ')


def connect_for_check(args, saved_reference=None):
    """Reconnect at a trial boundary; never reuse partial calibration or samples."""
    while True:
        stream = sock = None
        try:
            sock = SerialTransport(args.serial_port)
            stream = SampleStream(sock, flex_count=5, sample_ms=10)
            stream.check_ready()
            if saved_reference is not None:
                print('NỐI LẠI: giữ mốc flex, giữ tay yên để lấy lại mốc MPU.', flush=True)
                reference = initialize_imu(stream, saved_reference)
            elif args.recalibrate:
                reference = calibrate(stream)
                if reference is None:
                    stream.close()
                    return None
            else:
                reference = initialize_imu(stream, json.loads(latest_reference().read_text(encoding='utf-8')))
            return stream, sock, reference
        except (ValueError, OSError, KeyError) as error:
            if stream:
                stream.close()
            elif sock:
                sock.close()
            print(f'KẾT NỐI/HIỆU CHUẨN LỖI: {str(error)[:250]}', flush=True)
            print('Không dùng dữ liệu lỗi. Kiểm tra cáp USB/đầu nối; đóng Serial Monitor.')
            command = input('Enter: kết nối lại | C: hiệu chuẩn flex lại nếu đã chỉnh găng | Q: dừng > ').strip().upper()
            if command == 'Q':
                return None
            if command == 'C':
                saved_reference = None
                args.recalibrate = True
        except BaseException:
            if stream:
                stream.close()
            elif sock:
                sock.close()
            raise


def save_observation(folder, record):
    if record.get('error'):
        return False
    # Ground truth stays separate from predictions. Raw data enables replay.
    with (folder / 'trials.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    path = folder / 'results.csv'
    new = not path.exists()
    with path.open('a', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(['Lượt', 'Câu định làm', 'Cửa sổ', 'Kết quả', 'Tự đánh giá', 'Lỗi', 'Thời điểm UTC'])
        writer.writerow([record['trial'], record['expected_sentence'], record['window_summary'],
                         record['result'], record['review'], record['error'], record['utc']])
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial-port', default='COM3')
    p.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    p.add_argument('--seconds', type=int, default=None, help='Optional legacy fixed duration')
    p.add_argument('--none-windows', type=int, default=10)
    p.add_argument('--min-votes', type=int, default=5)
    p.add_argument('--recalibrate', action='store_true')
    add_speech_arguments(p)
    args = p.parse_args(argv)
    if (args.seconds is not None and not 2 <= args.seconds <= 15) or args.min_votes < 1 or args.none_windows < 1:
        p.error('seconds: 2..15; min-votes >= 1')
    folder = Path(__file__).resolve().parents[1] / 'outputs' / 'sentence_checks' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
    stream = sock = None
    try:
        counts = update_excel()
        model = SequenceModel(args.model)
        connected = connect_for_check(args)
        if connected is None:
            return 0
        stream, sock, reference = connected
        speaker = ESP32Speaker(stream, args.speech_voice, args.speech_volume) if args.speak else None
        if speaker:
            speaker.check_ready()
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'session.json').write_text(json.dumps({
            'model': str(args.model.resolve()), 'manifest': model.manifest,
            'reference': reference, 'seconds': args.seconds, 'min_votes': args.min_votes,
            'none_windows': args.none_windows, 'end_mode': 'fixed' if args.seconds else 'consecutive_none',
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'MODEL: {args.model}\nFILE EXCEL DUY NHẤT: {WORKBOOK}', flush=True)
        print('Nhập câu đúng trước khi làm. Máy không dùng câu nhập để ép kết quả dự đoán.')
        expected = ''
        trial = 0
        while True:
            value = input('\nCâu định làm (Enter: lặp câu trước; /Q: dừng) > ').strip()
            if value.upper() == '/Q':
                break
            if value:
                expected = value
            if not expected:
                continue
            number = counts[sentence_key(expected)] + 1
            input(f'CÂU: {expected} | LƯỢT HỢP LỆ {number} (đã lưu {number-1}). Enter để đếm ngược > ')
            trial += 1
            record = dict(trial=trial, expected_sentence=expected, rows=[], window_predictions=[],
                          words=[], word_runs=[], window_summary='', result='', error='',
                          reference=reference,
                          review='Chưa đánh giá', utc=datetime.now(timezone.utc).isoformat())
            try:
                stream.check_ready()
                countdown()
                try:
                    cursor = stream.start_trial()
                    if args.seconds is None:
                        print(f'BAT DAU: lam cau lien tuc; {args.none_windows} NONE lien tiep de ket thuc. Enter: chot thu cong.', flush=True)
                        captured = capture_until_none(stream, cursor, model, reference, args.none_windows)
                        record['rows'] = captured.rows
                        votes = captured.votes
                        words, runs = filter_window_predictions(votes, args.min_votes)
                        record['end_reason'] = 'none' if captured.done else 'manual'
                    else:
                        print(f'BAT DAU: thu {args.seconds} giay.', flush=True)
                        record['rows'] = stream.capture(args.seconds, sample_count=args.seconds * 100, after=cursor)
                        words, votes, runs = decode_five_seconds(record['rows'], model, reference, args.min_votes)
                finally:
                    stream.sock.sendall(b'STOP\n')
                record.update(words=words, window_predictions=votes, word_runs=runs,
                              result=format_sentence(words), window_summary=', '.join(
                                  f'{WORD_TEXT.get(label, label)}×{count}' for label, count in runs))
                print(f"CÂU ĐÚNG: {expected}\nCỬA SỔ: {record['window_summary']}\nMÁY ĐOÁN: {record['result']}", flush=True)
            except (ValueError, OSError, KeyError) as error:
                record['error'] = str(error)
                print(f'LỖI LƯỢT {trial}: {error}. ĐÃ BỎ, KHÔNG LƯU.', flush=True)
                if stream.error or stream.recovery_required:
                    print('Lượt lỗi đã bỏ. Đóng COM và kết nối lại; giữ nguyên găng tay.', flush=True)
                    stream.close()
                    stream = sock = None
                    connected = connect_for_check(args, reference)
                    if connected is None:
                        break
                    stream, sock, reference = connected
                    if speaker:
                        speaker = ESP32Speaker(stream, args.speech_voice, args.speech_volume)
                        speaker.check_ready()
                    print('ĐÃ NỐI LẠI. Câu và số lượt hợp lệ được giữ; Enter để thử lại câu.')
                continue
            # Persist before asking for input, so Ctrl+C cannot discard the observation.
            save_observation(folder, record)
            if speaker:
                speaker.speak_result(record['result'], record['words'])
            counts = update_excel()
            if stream.error or stream.recovery_required:
                print('Cần khởi động lại để lấy mốc cảm biến. Các lượt trước đã lưu.')
                break
            review = input('Đánh giá: D đúng / S sai / L làm lỗi / Enter chưa rõ > ').strip().upper()
            # Separate annotation file preserves the original prediction record.
            with (folder / 'reviews.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps({'trial': trial, 'review': review}, ensure_ascii=False) + '\n')
            path = folder / 'results.csv'
            with path.open(encoding='utf-8-sig', newline='') as f:
                table = list(csv.reader(f))
            table[-1][4] = {'D': 'Đúng', 'S': 'Sai', 'L': 'Thao tác lỗi'}.get(review, 'Chưa rõ')
            temp = path.with_suffix('.tmp')
            with temp.open('w', encoding='utf-8-sig', newline='') as f:
                csv.writer(f).writerows(table)
            temp.replace(path)
            counts = update_excel()
            print(f'ĐÃ LƯU LƯỢT {counts[sentence_key(expected)]} CỦA CÂU NÀY VÀO {WORKBOOK.name}. Enter để lặp câu.')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nĐã dừng; các lượt đã ghi vẫn được giữ.')
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(f'DỪNG: {error}')
        return 1
    finally:
        if stream:
            stream.close()
        elif sock:
            sock.close()
        if folder.exists():
            print(f'FILE THỐNG KÊ: {WORKBOOK}')


if __name__ == '__main__':
    raise SystemExit(main())
