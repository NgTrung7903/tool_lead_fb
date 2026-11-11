"""Module xuất dữ liệu bình luận và lead ra file Excel (.xlsx) chuẩn hóa.
Tự động định dạng:
- Chia rõ ràng từng field: ID, Phân loại, Điểm số, SĐT chuẩn hóa, Khách hàng, Email, Zalo, Lý do lọc, Tín hiệu, Nội dung gốc, Nguồn, Thời gian, Trạng thái.
- Định dạng màu sắc trực quan (Xanh lá: Lead Tiềm Năng, Vàng: Cần Duyệt, Xám: Bỏ Qua).
- Tự căn chỉnh độ rộng cột và bọc dòng (wrap text).
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


# Bảng màu chuyên nghiệp
HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")  # Slate 800
HEADER_FONT = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")

LEAD_FILL = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")    # Emerald 100
REVIEW_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # Amber 100
IGNORE_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")  # Slate 100

THIN_BORDER = Border(
    left=Side(style='thin', color='CBD5E1'),
    right=Side(style='thin', color='CBD5E1'),
    top=Side(style='thin', color='CBD5E1'),
    bottom=Side(style='thin', color='CBD5E1')
)


def _append_literal_row(ws, values):
    """Keep imported text literal, including strings beginning with '='."""
    cleaned = []
    for value in values:
        if isinstance(value, str):
            value = ILLEGAL_CHARACTERS_RE.sub('', value)
            if len(value) > 32767:
                raise ValueError('Một ô vượt giới hạn 32.767 ký tự của Excel.')
        cleaned.append(value)
    ws.append(cleaned)
    for cell, value in zip(ws[ws.max_row], cleaned):
        if isinstance(value, str):
            cell.data_type = 's'


def _save_workbook(wb, output):
    if not hasattr(output, 'write'):
        Path(output).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return output


def _write_records_sheet(wb, records, title):
    """Xuất danh sách bản ghi đã lọc sang file Excel hoàn chỉnh."""
    ws = wb.create_sheet(title)

    # 1. Định nghĩa các cột (Fields) rõ ràng theo yêu cầu nghiệp vụ
    headers = [
        "STT",
        "Mã Bản Ghi",
        "Phân Loại (Classification)",
        "Điểm Đánh Giá (Score)",
        "Số Điện Thoại",
        "Tên Khách Hàng",
        "Zalo",
        "Email",
        "Lý Do Lọc Chi Tiết (Reason Summary)",
        "Tín Hiệu Khớp (Signals)",
        "Nội Dung Gốc (Bình Luận / Bài Viết)",
        "Nguồn Dữ Liệu (Source URL/Group)",
        "Thời Gian Ghi Nhận",
        "Trạng Thái Xử Lý",
        "Mã Căn", "Mã Lead Revoland", "Đồng Bộ (Theo Dữ Liệu Nhập)", "Loại Bản Ghi",
        "Mã Chiến Dịch", "Mã Tác Vụ Đăng", "Tên Nhóm", "URL Tin Nguồn", "URL Bình Luận",
        "Mức quan tâm", "Cụm từ đánh giá mức độ", "Loại tác giả", "Kênh liên hệ"
    ]

    ws.append(headers)

    # Style Header Row
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 28

    # 2. Đổ dữ liệu từng dòng
    for idx, r in enumerate(records, start=1):
        classification = r.get("classification", "IGNORE")
        score = r.get("score", 0.0)

        # Lấy SĐT, Zalo, Email
        contacts = r.get("contacts", {})
        phone = contacts.get("primary_phone") or r.get("phone_number") or ""
        zalo = contacts.get("zalo") or ""
        email = "\n".join(contacts["emails"]) if contacts.get("emails") else r.get("email", "")

        # Lý do
        reasons_list = r.get("reasons", [])
        reasons_text = "\n• ".join(reasons_list) if reasons_list else r.get("intent_summary", "")
        if reasons_text and not reasons_text.startswith("• "):
            reasons_text = "• " + reasons_text

        # Tín hiệu
        signals = r.get("signals", {})
        signal_tokens = []
        if signals.get("intents"):
            for k, vals in signals["intents"].items():
                signal_tokens.append(f"Ý định: {', '.join(vals)}")
        if signals.get("variants"):
            for k, vals in signals["variants"].items():
                signal_tokens.append(f"Từ khóa: {', '.join(vals)}")
        if signals.get("locations"):
            signal_tokens.append(f"Khu vực: {', '.join(signals['locations'])}")
        signals_text = " | ".join(signal_tokens) if signal_tokens else "-"

        # Trạng thái
        status = {'LEAD_POTENTIAL': 'Lead tiềm năng', 'NEEDS_REVIEW': 'Cần xem xét',
                  'IGNORE': 'Bỏ qua'}.get(classification, classification)
        if r.get('sync_status') == 'synced' and r.get('revoland_lead_id'):
            status = 'Đã đồng bộ theo bản ghi'
        elif r.get('sync_status') == 'failed':
            status = 'Đồng bộ thất bại'

        row_data = [
            idx,
            r.get("id") or r.get("comment_id") or r.get("revoland_lead_id") or f"REC_{idx:03d}",
            classification,
            score,
            phone,
            r.get("fb_user_name") or r.get("customer_name") or "Khách hàng",
            zalo,
            email,
            reasons_text,
            signals_text,
            r.get("raw_content") or r.get("text") or "",
            r.get("source_url") or r.get("source_type") or "Facebook / Revoland",
            r.get("created_at") or "",
            status, r.get('listing_id') or '', r.get('revoland_lead_id') or '',
            r.get('sync_status') or 'not_synced', r.get('record_type') or 'comment',
            r.get('campaign_id') or '', r.get('posting_task_id') or '', r.get('group_name') or '',
            r.get('listing_source_url') or '', r.get('comment_url') or '',
            {'strong':'Mạnh','moderate':'Vừa','weak':'Yếu','unclear':'Chưa rõ','none':'Chưa thấy nhu cầu'}.get(r.get('interest_level'), 'Chưa rõ'),
            ', '.join(r.get('interest_evidence', [])),
            {'anonymous':'Ẩn danh','known':'Tên hiển thị','unknown':'Chưa xác định'}.get(r.get('identity_status'), 'Chưa xác định'),
            ', '.join({'phone':'Có SĐT','zalo':'Có Zalo','email':'Có email','profile':'Có link hồ sơ','comment':'Có link comment'}.get(c,c) for c in r.get('contact_channels', []))
        ]

        _append_literal_row(ws, row_data)
        current_row = idx + 1
        ws.row_dimensions[current_row].height = min(300, max(42, 28 * r.get('comment_count', 1)))

        # Format cell style và màu nền theo phân loại
        fill = IGNORE_FILL
        if classification == "LEAD_POTENTIAL":
            fill = LEAD_FILL
        elif classification == "NEEDS_REVIEW":
            fill = REVIEW_FILL

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.border = THIN_BORDER
            cell.font = Font(name="Segoe UI", size=10)
            cell.alignment = Alignment(vertical="center", wrap_text=True)

            # Cột Phân loại & Trạng thái có nền màu
            if col_idx in [3, 14]:
                cell.fill = fill
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.font = Font(name="Segoe UI", size=10, bold=True)
            elif col_idx in [1, 4, 5]:
                cell.alignment = Alignment(horizontal="center", vertical="center")

    # 3. Tự động điều chỉnh độ rộng các cột
    col_widths = {
        1: 6,   # STT
        2: 16,  # Mã
        3: 20,  # Phân loại
        4: 12,  # Điểm
        5: 16,  # SĐT
        6: 18,  # Tên
        7: 14,  # Zalo
        8: 20,  # Email
        9: 40,  # Lý do
        10: 30, # Tín hiệu
        11: 45, # Nội dung gốc
        12: 24, # Nguồn
        13: 22, # Thời gian
        14: 28, 15: 20, 16: 24, 17: 28, 18: 18, 19: 38, 20: 38, 21: 28, 22: 48, 23: 48,
        24: 22, 25: 45, 26: 24, 27: 42
    }

    for col_idx, width in col_widths.items():
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    return ws


def export_records_to_excel(records: List[Dict[str, Any]], output_path: str) -> str:
    """One customer per row, including all source groups and posts."""
    from services.customer_records import aggregate_customers
    rows = aggregate_customers(records)
    for row in rows:
        if len(row['sources']) > 1:
            row['raw_content'] = '\n\n'.join('\n'.join(filter(None, (
                comment.get('group_name'), comment.get('source_url'),
                comment.get('raw_content') or comment.get('text')))) for comment in row['comments'])
        for field in ('source_url', 'group_name', 'campaign_id', 'posting_task_id', 'listing_source_url'):
            row[field] = '\n'.join(dict.fromkeys(source[field] for source in row['sources'] if source.get(field)))
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _write_records_sheet(wb, rows, 'Khách hàng')
    return _save_workbook(wb, output_path)



def export_campaigns_to_excel(campaigns, output_path):
    """Export a snapshot of posting history; one row per group task."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Kết quả đăng bài'
    headers = ['Mã chiến dịch', 'Mã căn', 'Tiêu đề căn', 'Nguồn dữ liệu', 'Trạng thái chiến dịch',
               'Mã tác vụ', 'Mã nhóm', 'Tên nhóm', 'URL nhóm', 'Trạng thái nhóm', 'URL bài đăng',
               'Lỗi / Ghi chú', 'Số lần thử lại', 'Tạo chiến dịch (UTC)', 'Xác nhận bài (UTC)',
               'Bằng chứng', 'Đã bắt đầu gửi', 'Tình trạng link hiện tại', 'Kiểm tra link (UTC)', 'Ghi chú kiểm tra link']
    ws.append(headers)
    for campaign in campaigns:
        for task in campaign.tasks:
            _append_literal_row(ws, [campaign.id, campaign.listing_id, campaign.listing_title,
                campaign.source_mode, campaign.status, task.task_id, task.group_id, task.group_name,
                task.group_url, task.status.value, task.post_url or '', task.error_message or '',
                task.retry_count, campaign.created_at, task.posted_at or '', task.evidence or '',
                'Có' if task.submission_started else 'Chưa', task.post_check_status,
                task.post_checked_at or '', task.post_check_message or ''])
    for row in ws:
        for cell in row:
            cell.font = HEADER_FONT if cell.row == 1 else Font(name='Segoe UI', size=10)
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            if cell.row == 1:
                cell.fill = HEADER_FILL
            cell.border = THIN_BORDER
    for index, width in enumerate([38,22,48,16,24,38,22,36,48,24,48,55,18,28,28,38,20,28,28,60],1):
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    return _save_workbook(wb, output_path)


def workbook_bytes(exporter, records):
    output = BytesIO()
    exporter(records, output)
    return output.getvalue()
