#!/usr/bin/env python3
"""CLI điều khiển Tool Đăng Bài Nhóm Facebook Từ Revoland.

Ví dụ sử dụng:
  1. Đăng nhập Facebook (mở trình duyệt để khách tự nhập mật khẩu & 2FA):
     python cli.py --login-fb

  2. Kiểm tra trạng thái phiên đăng nhập:
     python cli.py --check-session

  3. Đăng xuất và xóa phiên:
     python cli.py --logout-fb

  4. Xem danh sách căn hộ từ Revoland:
     python cli.py --list-listings

  5. Xem danh sách nhóm Facebook:
     python cli.py --list-groups

  6. Đăng 1 căn lên các nhóm (kèm chống trùng):
     python cli.py --post --listing rev_listing_001

  7. Khởi động Web Dashboard:
     python cli.py --server
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import uuid
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent

from services.campaign_service import CampaignService
from services.group_manager import GroupManager
from services.revoland_service import RevolandService
from services.session_manager import FacebookSessionManager
from config.settings import RUNTIME_DIR
from services.report_service import load_comment_json, prepare_comment_report, campaign_report_data
from services.excel_exporter import export_records_to_excel, export_campaigns_to_excel


def main():
    parser = argparse.ArgumentParser(description="Facebook Lead Filter và công cụ đăng bài cũ")
    parser.add_argument("--login-fb", action="store_true", help="Mở trình duyệt để khách tự đăng nhập Facebook")
    parser.add_argument('--login-timeout', type=int, default=600, help='Thời gian chờ đăng nhập, từ 30 đến 1800 giây')
    parser.add_argument('--page-test', action='store_true', help='Chuẩn bị/đăng một bài kiểm thử trên Trang bằng code project')
    parser.add_argument('--source-json', help='File dữ liệu QuinLand cho bài kiểm thử Trang')
    parser.add_argument('--page-url', help='URL Trang Facebook dạng people/.../ID hoặc profile.php?id=ID')
    parser.add_argument('--page-name', help='Tên Trang cần khớp danh tính trong ô soạn bài')
    parser.add_argument('--page-session', action='store_true', help='Giữ cửa sổ phiên của tool mở để người dùng tự kiểm tra tài khoản/Trang')
    parser.add_argument('--page-run', help='Mã bài kiểm thử đã chuẩn bị')
    parser.add_argument('--submit-page-test', action='store_true', help='Thực sự gửi bài kiểm thử đã chuẩn bị')
    parser.add_argument("--check-session", action="store_true", help="Kiểm tra trạng thái phiên Facebook hiện tại")
    parser.add_argument("--logout-fb", action="store_true", help="Đăng xuất và xóa sạch dữ liệu phiên Facebook trên máy")
    parser.add_argument("--list-listings", action="store_true", help="Lấy danh sách căn đã đăng trên Revoland")
    parser.add_argument("--list-groups", action="store_true", help="Lấy danh sách nhóm Facebook mục tiêu")
    parser.add_argument("--post", action="store_true", help="Khởi chạy đăng bài")
    parser.add_argument("--listing", type=str, help="Mã ID căn hộ cần đăng")
    parser.add_argument("--groups", type=str, help="Danh sách ID nhóm (cách nhau dấu phẩy)")
    parser.add_argument("--retry", type=str, help="Mã chiến dịch cần thử lại các nhóm thất bại")
    parser.add_argument("--server", action="store_true", help="Khởi chạy Web Dashboard tại http://localhost:8000")
    parser.add_argument('--port', type=int, default=8000, help='Cổng dashboard cục bộ')
    exports = parser.add_mutually_exclusive_group()
    exports.add_argument('--export-posts', action='store_true', help='Xuất kết quả đăng bài ra Excel')
    exports.add_argument('--export-comments', metavar='JSON_FILE', help='Lọc bình luận JSON và xuất Excel, không gọi Revoland')
    parser.add_argument('--campaign', help='Chỉ xuất một chiến dịch (dùng với --export-posts)')
    parser.add_argument('--output', help='Đường dẫn file .xlsx; mặc định trong data/exports của khách')

    args = parser.parse_args()

    if args.page_session:
        if not args.page_url or not 30 <= args.login_timeout <= 1800:
            parser.error('--page-session cần --page-url và --login-timeout từ 30 đến 1800 giây.')
        from services.page_post_service import open_page_session
        open_page_session(args.page_url, args.login_timeout)
        return

    if args.page_test:
        from services.page_post_service import PagePostService
        service = PagePostService()
        try:
            if args.page_run:
                result = service.submit(args.page_run) if args.submit_page_test else service.get(args.page_run)
            else:
                if args.submit_page_test or not all((args.source_json, args.page_url, args.page_name)):
                    parser.error('Chuẩn bị cần --source-json, --page-url, --page-name; gửi cần --page-run ID --submit-page-test.')
                result = service.prepare(args.source_json, args.page_url, args.page_name)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.export_posts or args.export_comments:
        if args.campaign and not args.export_posts:
            parser.error('--campaign cần dùng cùng --export-posts.')
        name = 'ket_qua_dang_bai' if args.export_posts else 'binh_luan_lead'
        output = Path(args.output) if args.output else RUNTIME_DIR / 'data' / 'exports' / (
            name + '_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6] + '.xlsx')
        if output.suffix.lower() != '.xlsx':
            parser.error('--output phải có đuôi .xlsx.')
        if output.exists():
            parser.error('File đích đã tồn tại. Chọn tên khác để tránh ghi đè báo cáo.')
        try:
            if args.export_posts:
                campaigns = campaign_report_data(CampaignService(recover_on_start=False), args.campaign)
                export_campaigns_to_excel(campaigns, output)
            else:
                records = prepare_comment_report(load_comment_json(args.export_comments))
                export_records_to_excel(records, output)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(f'Đã xuất Excel: {output.resolve()}')
        return

    session_mgr = FacebookSessionManager()
    revo_svc = RevolandService()
    group_mgr = GroupManager()
    camp_svc = CampaignService(revoland_service=revo_svc, group_manager=group_mgr)

    if args.server:
        print(f"Đang khởi động Web Dashboard tại: http://127.0.0.1:{args.port}")
        import uvicorn
        uvicorn.run("api.server:app", host="127.0.0.1", port=args.port, reload=False, workers=1)
        return

    if args.login_fb:
        if not 30 <= args.login_timeout <= 1800:
            parser.error('--login-timeout cần từ 30 đến 1800 giây.')
        print("Đang mở trình duyệt để khách đăng nhập Facebook (có hỗ trợ 2FA)...")
        res = session_mgr.open_interactive_login(timeout_seconds=args.login_timeout)
        print(f"-> {res['message']}")
        return

    if args.check_session:
        st = session_mgr.check_session_status()
        print(f"Trạng thái phiên: {st.status_text}")
        if st.user_name:
            print(f"Tài khoản: {st.user_name}")
        return

    if args.logout_fb:
        res = session_mgr.logout_and_clear_session()
        print(f"-> {res['message']}")
        return

    if args.list_listings:
        items = revo_svc.get_listings()
        print(f"\nDanh sách {len(items)} căn trên Revoland:")
        for it in items:
            print(f"  [{it.id}] {it.code} - {it.title}")
            print(f"       Giá: {it.price_text} | Khu vực: {it.location}")
        return

    if args.list_groups:
        groups = group_mgr.list_groups()
        print(f"\nDanh sách {len(groups)} nhóm Facebook mục tiêu:")
        for g in groups:
            print(f"  [{g.id}] {g.name}")
            print(f"       URL: {g.group_url}")
        return

    if args.post:
        listings = revo_svc.get_listings()
        listing_id = args.listing or (listings[0].id if listings else None)
        if not listing_id:
            print("Lỗi: Không tìm thấy căn hộ nào để đăng.")
            return

        groups = group_mgr.list_groups()
        if args.groups:
            target_ids = [gid.strip() for gid in args.groups.split(",") if gid.strip()]
        else:
            target_ids = [g.id for g in groups[:2]]  # Mặc định lấy 2 nhóm đầu

        print(f"Khởi tạo chiến dịch đăng căn [{listing_id}] lên {len(target_ids)} nhóm...")
        camp = camp_svc.create_campaign(listing_id, target_ids)
        print(f"Đang thực thi chiến dịch {camp.id}...")
        res_camp = camp_svc.execute_campaign(camp.id)
        print(f"Kết quả chiến dịch: {res_camp.status.upper()}")
        for t in res_camp.tasks:
            print(f"  - [{t.status.value.upper()}] {t.group_name} | {t.post_url or t.error_message}")
        return

    if args.retry:
        print(f"Đang thử lại các nhóm thất bại trong chiến dịch {args.retry}...")
        res_camp = camp_svc.retry_failed_tasks(args.retry)
        print(f"Kết quả sau retry: {res_camp.status.upper()}")
        for t in res_camp.tasks:
            print(f"  - [{t.status.value.upper()}] {t.group_name} | Retry: {t.retry_count}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
