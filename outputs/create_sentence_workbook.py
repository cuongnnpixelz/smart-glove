from pathlib import Path
import json
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo

base = Path(__file__).resolve().parents[1]
labels = {
    'TOI': 'TÔI', 'BAN': 'BẠN', 'KHOE': 'KHỎE', 'CHAO': 'CHÀO',
    'CAM_ON': 'CẢM ƠN', 'DIEN_THOAI': 'ĐIỆN THOẠI', 'THICH': 'THÍCH',
    'BUON_BA': 'BUỒN BÃ', 'TEN': 'TÊN', 'GI': 'GÌ', 'DANG_LAM': 'ĐANG LÀM',
}
# Explicit display proposals, not claims about sign-language grammar or live decoder support.
rows = [
('Chào hỏi','CHAO','Xin chào!','Xin','Chào ngắn; một ký hiệu.'),
('Chào hỏi','CHAO BAN','Chào bạn!','',''),
('Chào hỏi','TOI CHAO BAN','Tôi chào bạn.','',''),
('Cảm ơn','CAM_ON','Cảm ơn!','',''),
('Cảm ơn','CAM_ON BAN','Cảm ơn bạn!','',''),
('Cảm ơn','TOI CAM_ON BAN','Tôi cảm ơn bạn.','','Ưu tiên thử chuỗi này.'),
('Sức khỏe','TOI KHOE','Tôi khỏe.','',''),
('Sức khỏe','BAN KHOE','Bạn khỏe không?','không','Theo quy ước câu hỏi bạn đã chọn; cùng chuỗi cũng có thể là lời khẳng định. Găng tay không tự biết ý hỏi.'),
('Cảm xúc','TOI BUON_BA','Tôi buồn bã.','','BUỒN BÃ còn nhầm trong kiểm tra model; cần thử trực tiếp.'),
('Cảm xúc','BAN BUON_BA','Bạn buồn bã.','','Lời nhận xét, không tự thêm dấu hỏi.'),
('Sở thích','TOI THICH BAN','Tôi thích bạn.','',''),
('Sở thích','BAN THICH TOI','Bạn thích tôi.','','Lời khẳng định, không tự chuyển thành câu hỏi.'),
('Sở thích','BAN THICH GI','Bạn thích gì?','',''),
('Sở thích','TOI THICH DIEN_THOAI','Tôi thích điện thoại.','',''),
('Sở thích','BAN THICH DIEN_THOAI GI','Bạn thích điện thoại gì?','','Hỏi loại điện thoại người kia thích; chưa có nhãn để trả lời tên hãng.'),
('Tên','BAN TEN GI','Bạn tên gì?','','Chỉ hỏi tên; chưa có từ vựng để trả lời tên riêng.'),
('Hoạt động','BAN DANG_LAM GI','Bạn đang làm gì?','','DANG_LAM là một nhãn đã thu, không tách thành hai nhãn.'),
('Hoạt động','TOI DANG_LAM GI','Tôi đang làm gì?','','Dùng khi đố người kia đoán hoạt động của mình.'),
('Hai câu liên tiếp','CHAO BAN / BAN TEN GI','Chào bạn! Bạn tên gì?','','Hai lượt riêng; kết thúc câu chào rồi làm câu hỏi.'),
('Hai câu liên tiếp','CHAO BAN / BAN KHOE','Chào bạn! Bạn khỏe không?','không','Hai lượt riêng; câu hỏi sức khỏe theo quy ước đã chọn.'),
('Hai câu liên tiếp','CHAO BAN / BAN DANG_LAM GI','Chào bạn! Bạn đang làm gì?','','Hai lượt riêng.'),
('Hai câu liên tiếp','CHAO BAN / BAN THICH GI','Chào bạn! Bạn thích gì?','','Hai lượt riêng.'),
('Hai câu liên tiếp','TOI KHOE / CAM_ON BAN','Tôi khỏe. Cảm ơn bạn!','','Hai lượt riêng.'),
('Hai câu liên tiếp','TOI CAM_ON BAN / TOI THICH BAN','Tôi cảm ơn bạn. Tôi thích bạn.','','Hai lượt riêng.'),
]
manifest=json.loads((base/'SmartSignLanguage/models/sequence_5_100hz_U4_U5_extra_trees_20261114_random10/manifest.json').read_text())
assert set(labels)==set(manifest['labels'])-{'NONE'}
wb=Workbook(); ws=wb.active; ws.title='Câu gợi ý'
ws.append(['STT','Nhóm','Thứ tự cử chỉ','Câu tiếng Việt hiển thị','Số ký hiệu','Từ thêm khi hiển thị','Số lượt thu 5s đề xuất','Ghi chú','Chuỗi nhãn code'])
for i,(group,seq,sentence,added,note) in enumerate(rows,1):
    tokens=seq.replace('/','').split()
    assert all(t in labels for t in tokens)
    gesture='  | KẾT THÚC CÂU |  '.join(' → '.join(labels[t] for t in part.split()) for part in seq.split('/'))
    ws.append([i,group,gesture,sentence,len(tokens),added or 'Không',len(seq.split('/')),note,seq])
v=wb.create_sheet('11 từ đã học'); v.append(['STT','Nhãn model','Hiển thị','Lưu ý'])
for i,(key,value) in enumerate(labels.items(),1):
    v.append([i,key,value,'Một nhãn hoàn chỉnh' if key in ('CAM_ON','DIEN_THOAI','BUON_BA','DANG_LAM') else ''])
n=wb.create_sheet('Cách dùng');n.append(['Mục','Nội dung'])
notes=[
('Phạm vi','24 gợi ý giao tiếp từ đúng 11 nhãn U4 + U5; gồm 18 câu/phát ngôn ngắn và 6 tổ hợp hai câu. Không phải mọi phép hoán vị đều có nghĩa.'),
('NONE','Là nhãn nền/nghỉ, không phải từ để ghép câu; không tính vào 11 từ.'),
('Trạng thái triển khai','Đây là bảng đề xuất, chưa cập nhật bộ ghép câu trong chương trình. Nhận diện được từng từ không bảo đảm tự hiển thị đúng mọi câu trong bảng.'),
('Ngữ pháp','Thứ tự cử chỉ là quy ước thử nghiệm cho ứng dụng hiện tại, không khẳng định là ngữ pháp chuẩn của các ngôn ngữ ký hiệu Việt Nam.'),
('Từ thêm','Xin/không là từ được đề xuất thêm khi hiển thị; model không nhận diện riêng các từ này. Không tự thêm các từ làm đổi nghĩa ngoài quy ước rõ ràng.'),
('Câu hỏi','Chuỗi BẠN KHỎE được đề xuất hiển thị câu hỏi theo yêu cầu trước của người dùng. Găng tay không đo nét mặt để phân biệt câu hỏi với khẳng định.'),
('Thu 5 giây','Một câu ngắn mỗi lượt 5 giây; làm tự nhiên, không ép cho kịp. Hai câu liên tiếp trong bảng nên thực hiện thành hai lượt riêng.'),
('Lặp nhãn','TÔI×6 → CẢM ƠN×1 → BẠN×5 có thể được gom thành TÔI CẢM ƠN BẠN theo bộ lọc đang thử. Không tự xóa từ lặp có chủ ý giữa hai câu.'),
('Tên riêng','Có nhãn TÊN và GÌ để hỏi tên, nhưng chưa có nhãn tên riêng hoặc bộ đánh vần để trả lời tên.'),
('Đang làm','DANG_LAM được xử lý như nhãn người dùng đã thu; bảng không xác nhận tính chuẩn ngôn ngữ ký hiệu của động tác đó.'),
('Đánh giá model','Model chung đạt 117/120 lượt test ngẫu nhiên: BUỒN BÃ nhầm ĐANG LÀM 2 lượt, KHỎE nhầm NONE 1 lượt. Test cùng các phiên thu, chưa chứng minh độ chính xác trực tiếp.'),
]
for row in notes:n.append(row)
for sheet,widths,table_name in [(ws,[7,22,64,45,13,24,22,75,56],'Sentences'),(v,[8,24,25,35],'Vocabulary'),(n,[26,115],'Instructions')]:
    sheet.freeze_panes='A2'; sheet.sheet_view.showGridLines=False
    for cell in sheet[1]:cell.font=Font(name='Calibri',bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='17365D')
    for row in sheet.iter_rows(min_row=2):
        for cell in row:cell.font=Font(name='Calibri',size=11);cell.alignment=Alignment(vertical='top',wrap_text=True)
        sheet.row_dimensions[row[0].row].height=60 if sheet==n else 48
    for i,width in enumerate(widths,1):sheet.column_dimensions[sheet.cell(1,i).column_letter].width=width
    table=Table(displayName=table_name,ref=sheet.dimensions);table.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True);sheet.add_table(table)
    sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
    sheet.print_title_rows='1:1'
path=base/'outputs/Cau_ghep_11_tu_U4_U5.xlsx';wb.save(path)
check=load_workbook(path);assert check['Câu gợi ý'].max_row==25 and check['11 từ đã học'].max_row==12
print(path);print('Validated: 24 sentence suggestions, 11 model labels, 3 sheets')
