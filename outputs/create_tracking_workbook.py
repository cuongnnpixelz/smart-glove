from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo

wb = Workbook()
ws = wb.active
ws.title = 'Theo dõi từng lượt'
ws.append(['Mã câu', 'Câu định làm — nhãn đúng', 'Lượt', 'Ngày giờ',
           'Thứ tự ký hiệu bạn thực hiện', 'CỬA SỔ — dán nguyên dòng',
           'KẾT QUẢ — dán nguyên dòng', 'Đúng / Sai / Chưa rõ',
           'Có làm trọn câu?', 'Từ chèn / mất / nhầm', 'Lỗi cảm biến hoặc ghi chú', 'Đường dẫn log'])
for i in range(1, 11):
    for trial in range(1, 11):
        ws.append([f'C{i:02}', None, trial] + [None] * 9)
plan = wb.create_sheet('Câu tự nhập')
plan.append(['Mã câu', 'Câu bạn tự chọn', 'Thứ tự ký hiệu thực hiện', 'Số lượt dự kiến', 'Ghi chú'])
for i in range(1, 11):
    plan.append([f'C{i:02}', None, None, 10, None])
guide = wb.create_sheet('Cách dùng')
guide.append(['Mục', 'Hướng dẫn'])
for row in [
    ('Mục đích', 'Quan sát model từng từ khi làm liên tục cả câu. Chưa huấn luyện hoặc tự sửa nhãn theo dự đoán.'),
    ('1. Chọn câu', 'Tự điền câu ở trang Câu tự nhập. Mỗi mã câu có sẵn 10 hàng theo dõi. Có thể thêm câu/hàng nếu cần.'),
    ('2. Ghi mục tiêu', 'Ghi câu định làm và thứ tự ký hiệu trước mỗi lượt. Đây là nhãn đúng do bạn xác định; không lấy chữ máy đoán làm nhãn đúng.'),
    ('3. Chạy dự đoán', 'python -m SmartSignLanguage.predict_sentence_words --serial-port COM3 --seconds 5 --min-votes 3 --recalibrate'),
    ('Chọn đúng chương trình', 'predict_sentence_words vừa ghi log cảm biến vừa đoán từ. collect_phrase_5 chỉ thu câu, không hiện chuỗi từ dự đoán.'),
    ('4. Dán kết quả', 'Làm liên tục trong lượt 5 giây. Dán nguyên dòng CỬA SỔ và KẾT QUẢ vào hàng tương ứng. Giữ cả NONE và những từ sai, không sửa lại.'),
    ('5. Ghi tình trạng', 'Đánh dấu nếu làm thiếu/sai động tác, bị cắt hết giờ hoặc có lỗi cảm biến. Những lượt này cần tách khỏi đánh giá nhận diện.'),
    ('Ví dụ minh họa, không phải dữ liệu thật', 'Mục tiêu: Tôi cảm ơn bạn. CỬA SỔ: TÔI×3, CHÀO×1, CẢM ƠN×1, BẠN×3. KẾT QUẢ: TÔI CẢM ƠN BẠN. Ghi chú: CHÀO bị chèn nhưng bộ lọc đã loại.'),
    ('Log để đối chiếu', 'Dữ liệu cảm biến, dự đoán cửa sổ và kết quả được lưu ở .runtime/fixed_sequence_join/<phiên>/trials.jsonl. Ghi đường dẫn nếu biết.'),
    ('Lưu ý số đếm', 'Các cửa sổ 1,5 giây chồng lấn nhau. TÔI×3 không phải ba động tác độc lập hoặc xác suất đúng.'),
    ('Phân tích sau', 'So sánh nhãn gốc và kết quả lọc để xác định nhầm từ, nhiễu chuyển tiếp hay lọc mất từ. Bảng này chưa xác nhận động tác đúng ngôn ngữ ký hiệu.'),
]:
    guide.append(row)
for sheet, widths, name in [
    (ws, [10, 36, 9, 22, 46, 65, 45, 24, 22, 45, 45, 45], 'Tracking'),
    (plan, [12, 45, 60, 20, 55], 'Plan'),
    (guide, [32, 115], 'Guide'),
]:
    sheet.freeze_panes = 'A2'
    sheet.sheet_view.showGridLines = False
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='17365D')
        cell.alignment = Alignment(wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
        sheet.row_dimensions[row[0].row].height = 55
    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[sheet.cell(1, i).column_letter].width = width
    table = Table(displayName=name, ref=sheet.dimensions)
    table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
    sheet.add_table(table)
out = Path(__file__).with_name('Theo_doi_ghep_tu_khi_lam_cau.xlsx')
wb.save(out)
assert load_workbook(out).worksheets[0].max_row == 101
print(out)
