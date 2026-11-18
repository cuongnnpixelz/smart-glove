"""One consolidated workbook, rebuilt from valid observation logs."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[1] / 'outputs'
WORKBOOK = ROOT / 'Thong_ke_thu_cau.xlsx'


def sentence_key(text):
    text = unicodedata.normalize('NFC', text).upper().replace('_', ' ')
    return ' '.join(text.strip(' .!?').split())


def observations(root):
    result = []
    for path in sorted(Path(root).glob('*/trials.jsonl')):
        reviews = {}
        review_path = path.parent / 'reviews.jsonl'
        if review_path.exists():
            for line in review_path.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    r = json.loads(line)
                    reviews[r['trial']] = {'D': 'Đúng', 'S': 'Sai', 'L': 'Thao tác lỗi'}.get(r['review'], 'Chưa rõ')
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get('error'):
                continue
            r['review'] = reviews.get(r['trial'], r.get('review', 'Chưa rõ'))
            r['session'] = path.parent.name
            result.append(r)
    return sorted(result, key=lambda r: (r.get('utc', ''), r['session'], r['trial']))


def export_workbook(root=ROOT / 'sentence_checks', output=WORKBOOK):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo
    rows = observations(root)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Các lượt thu'
    ws.append(['STT', 'Câu định làm', 'Lượt của câu', 'Thời gian Việt Nam',
               'CỬA SỔ máy đoán', 'KẾT QUẢ sau lọc', 'Bạn đánh giá', 'Phiên', 'Mã lượt gốc'])
    counts = Counter()
    for index, r in enumerate(rows, 1):
        key = sentence_key(r['expected_sentence'])
        counts[key] += 1
        stamp = datetime.fromisoformat(r['utc']).astimezone(timezone(timedelta(hours=7)))
        ws.append([index, r['expected_sentence'], counts[key], stamp.strftime('%d/%m/%Y %H:%M:%S'),
                   r['window_summary'], r['result'], r['review'], r['session'], r['trial']])
    ws.freeze_panes = 'C2'
    ws.sheet_view.showGridLines = False
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='17365D')
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if isinstance(cell.value, str):
                cell.data_type = 's'
        ws.row_dimensions[row[0].row].height = 48
    for i, width in enumerate([8, 35, 16, 23, 80, 40, 22, 35, 16], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = width
    if rows:
        table = Table(displayName='SentenceTrials', ref=ws.dimensions)
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
        ws.add_table(table)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp.xlsx')
    wb.save(temporary)
    temporary.replace(output)
    return counts


if __name__ == '__main__':
    counts = export_workbook()
    print(f'{WORKBOOK}\nValid trials: {sum(counts.values())}')
