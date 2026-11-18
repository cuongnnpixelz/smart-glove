from collections import Counter, defaultdict
from pathlib import Path
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from SmartSignLanguage.sentence_check_excel import observations, ROOT


def normalized(text):
    text = unicodedata.normalize('NFC', text).upper().replace('_', ' ')
    return ' '.join(re.sub(r'[^\w\s]', ' ', text).split())


records = observations(ROOT / 'sentence_checks')
wb = Workbook()
summary = wb.active
summary.title = 'Tổng hợp theo câu'
summary.append(['Câu bạn nhập', 'Tổng lượt', 'Lượt so sánh được', 'Khớp câu', 'Không khớp',
                'Tỷ lệ khớp', 'Bạn đánh giá Đúng', 'Bạn đánh giá Sai', 'Làm lỗi',
                'Chưa đánh giá rõ', 'Kết quả máy thường xuất hiện', 'Ghi chú'])
detail = wb.create_sheet('Chi tiết từng lượt')
detail.append(['STT', 'Câu đúng bạn nhập', 'Lượt của câu', 'CỬA SỔ máy đoán',
               'KẾT QUẢ sau lọc', 'Đối chiếu câu', 'Bạn tự đánh giá', 'Ghi chú',
               'Thời gian Việt Nam', 'Phiên', 'Mã lượt gốc'])
groups = defaultdict(list)
counts = Counter()
for index, r in enumerate(records, 1):
    key = normalized(r['expected_sentence'])
    counts[key] += 1
    unclear = key in ('D', 'S', 'L', '')
    operation_error = r['review'] == 'Thao tác lỗi'
    eligible = not unclear and not operation_error
    match = normalized(r['result']) == key
    status = ('Chưa xác định câu đúng' if unclear else 'Loại: thao tác lỗi' if operation_error
              else 'Đúng — khớp câu' if match else 'Sai — không khớp câu')
    note = 'Nhãn nhập là ký tự điều khiển; không tự suy đoán câu định làm.' if unclear else ''
    if eligible and ((r['review'] == 'Đúng' and not match) or (r['review'] == 'Sai' and match)):
        note += ' Đánh giá của bạn khác đối chiếu chữ; cần xem lại.'
    stamp = datetime.fromisoformat(r['utc']).astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S')
    detail.append([index, r['expected_sentence'], counts[key], r['window_summary'], r['result'],
                   status, r['review'], note, stamp, r['session'], r['trial']])
    groups[key].append((r, eligible, match))

for key, group in groups.items():
    n = sum(e for _, e, _ in group)
    correct = sum(e and m for _, e, m in group)
    reviews = Counter(r['review'] for r, _, _ in group)
    outputs = Counter(r['result'] for r, _, _ in group)
    summary.append([key, len(group), n, correct, n-correct, correct/n if n else None,
                    reviews['Đúng'], reviews['Sai'], reviews['Thao tác lỗi'],
                    sum(v for k, v in reviews.items() if k not in ('Đúng', 'Sai', 'Thao tác lỗi')),
                    '\n'.join(f'{k}: {v} lượt' for k,v in outputs.most_common()),
                    'Cần xác nhận nhãn D là câu nào; không đưa vào tỷ lệ khớp.' if key == 'D' else
                    'Chỉ đánh giá chữ đầu ra, không xác minh động tác/ngữ pháp ký hiệu.'])
    summary.cell(summary.max_row, 6).number_format = '0.0%'
notes = wb.create_sheet('Cách đọc đánh giá')
notes.append(['Mục', 'Giải thích'])
for row in [
    ('Nguồn', 'Tất cả trials.jsonl hợp lệ trong outputs/sentence_checks, ghép với đánh giá cuối cùng trong reviews.jsonl. Không tạo lượt giả.'),
    ('Đúng / Sai tự động', 'So sánh câu bạn nhập với kết quả sau lọc; bỏ khác biệt hoa/thường, dấu câu, dấu gạch dưới và khoảng trắng. Không tự thêm, xóa hoặc đổi thứ tự từ.'),
    ('Đánh giá của bạn', 'Giữ riêng D=Đúng, S=Sai, L=Thao tác lỗi. Không thay đánh giá người dùng bằng kết quả so sánh chữ.'),
    ('Lượt lỗi', 'Lỗi cảm biến có trường error bị loại. Lượt bạn đánh dấu thao tác lỗi vẫn hiện để đối chiếu nhưng không tính tỷ lệ khớp.'),
    ('Nhãn D', 'Có 10 lượt nhập câu đúng là D. Chưa biết câu thực hiện là gì, nên không tự đổi thành Bạn khỏe không và không tính độ chính xác cho nhóm này.'),
    ('Tỷ lệ khớp', 'Số lượt khớp chữ / số lượt có nhãn câu xác định và không bị đánh dấu thao tác lỗi. Đây là thống kê các lượt đã thu, không phải kết quả test độc lập.'),
    ('Cửa sổ', 'CỬA SỔ giữ nguyên các nhãn lặp, nhãn sai và NONE để thấy vì sao sau lọc có hoặc mất từ. Số cửa sổ không phải số động tác độc lập.'),
    ('Phạm vi', 'Báo cáo này không sửa dữ liệu gốc, không train model và không xác nhận tính chuẩn ngôn ngữ ký hiệu.'),
]: notes.append(row)
for sheet, widths, name in [
    (summary,[32,13,19,14,16,16,20,20,15,21,65,55],'Summary'),
    (detail,[8,34,18,90,45,28,23,65,24,34,16],'Details'),
    (notes,[28,120],'Explanation'),
]:
    sheet.freeze_panes='C2' if sheet==detail else 'B2'
    sheet.sheet_view.showGridLines=False
    for c in sheet[1]:
        c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='17365D');c.alignment=Alignment(wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        for c in row:
            c.alignment=Alignment(wrap_text=True,vertical='top')
            if isinstance(c.value,str): c.data_type='s'
        sheet.row_dimensions[row[0].row].height=95 if sheet==summary else 60
    for i,width in enumerate(widths,1):sheet.column_dimensions[sheet.cell(1,i).column_letter].width=width
    table=Table(displayName=name,ref=sheet.dimensions)
    table.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True);sheet.add_table(table)
    sheet.print_title_rows='1:1'
out=ROOT/'Danh_gia_nhan_dien_cau_20261115.xlsx'
wb.save(out)
assert load_workbook(out).worksheets[1].max_row==len(records)+1
print('Trials:',len(records),'Sentence labels:',len(groups))
for key,group in groups.items():
    print(ascii(key),'matches',sum(e and m for _,e,m in group),'/',sum(e for _,e,_ in group))
print(out)
