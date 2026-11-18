"""Incremental 150-sample windows; end on consecutive background predictions."""
import time

from .runtime_flex_quality import recognition_quality


def manual_finish():
    try:
        import msvcrt
    except ImportError:
        return False
    return msvcrt.kbhit() and msvcrt.getwch() == '\r'


class NoneSentenceDecoder:
    def __init__(self, model, reference, none_windows=10):
        if none_windows < 1:
            raise ValueError('none_windows must be positive')
        self.model, self.reference = model, reference
        self.target = none_windows
        self.rows, self.votes = [], []
        self.none_count = 0
        self.done = False
        self.waiting_clean_flex = False

    def push(self, row):
        if self.done:
            raise ValueError('Sentence already complete')
        if self.rows and not 0 < float(row['timestamp']) - float(self.rows[-1]['timestamp']) <= 20:
            raise ValueError('Mat mau cam bien; huy luot, khong luu')
        self.rows.append(row)
        if len(self.rows) < 150 or (len(self.rows) - 150) % 25:
            return None
        window = self.rows[-150:]
        try:
            recognition_quality(window, self.reference)
        except ValueError as error:
            if 'NGHI LOI FLEX' not in str(error):
                raise
            # Never bridge a missing gesture or count corrupt data as NONE.
            self.votes.clear()
            self.none_count = 0
            if not self.waiting_clean_flex:
                print('FLEX NHIEU: bo doan loi va cau dang do; cho du lieu sach. '
                      'Khi san sang, lam lai cau.', flush=True)
            self.waiting_clean_flex = True
            return None
        if self.waiting_clean_flex:
            self.waiting_clean_flex = False
            # The first clean window is recovery evidence, not a new word.
            print('FLEX DA ON DINH: san sang, hay lam lai cau tu dau.', flush=True)
            return None
        label = self.model.predict(window, self.reference)
        self.votes.append(label)
        previous = self.none_count
        self.none_count = previous + 1 if label == 'NONE' else 0
        if self.none_count or previous:
            print(f'CHO KET THUC: {self.none_count}/{self.target}', flush=True)
        self.done = self.none_count >= self.target
        return label


def capture_until_none(stream, cursor, model, reference, none_windows=10):
    decoder = NoneSentenceDecoder(model, reference, none_windows)
    last_data = time.monotonic()
    while True:
        cursor, batch = stream.read_since(cursor, timeout=.1)
        if not batch and time.monotonic() - last_data > 3:
            raise ValueError('Khong nhan du lieu cam bien trong 3 giay; huy luot')
        if batch:
            last_data = time.monotonic()
        for row in batch:
            decoder.push(row)
            if decoder.done:
                return decoder
        if manual_finish() and decoder.votes:
            print('CHOT CAU BANG ENTER.', flush=True)
            return decoder
