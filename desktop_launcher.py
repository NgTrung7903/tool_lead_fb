"""Double-click entry point for the Windows executable."""
import argparse
import json
import logging
import multiprocessing
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
import webbrowser
import http.client
from urllib.parse import urlsplit

from build_info import BUILD_ID


def configure_runtime(customer):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', customer):
        raise ValueError('Tên khách chỉ dùng chữ, số, gạch ngang/gạch dưới, tối đa 48 ký tự.')
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    runtime = Path(os.environ.setdefault('REVOLAND_DATA_DIR', str(base / 'RevolandFBPoster' / customer))).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    if getattr(sys, 'frozen', False):
        # Only code/assets/browser binaries are unpacked beside _MEIPASS.
        # Customer credentials and history must stay in persistent user storage.
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(Path(sys._MEIPASS) / 'bundled-browsers')
    return runtime


def offline_self_test(output):
    """Verify packaged resources and browser without contacting external sites."""
    from config.settings import ROOT_DIR, RUNTIME_DIR
    from core.filter_engine import RegistryFilterEngine
    from services.report_service import comment_report_bytes, COMMENT_EXAMPLE
    from services.facebook_browser import launch_context
    from services.campaign_service import CampaignService
    from services.facebook_comment_collector import FacebookCommentCollector
    from playwright.sync_api import sync_playwright
    import openpyxl
    from io import BytesIO
    result = {'frozen':bool(getattr(sys, 'frozen', False))}
    result['html'] = (ROOT_DIR / 'api' / 'static' / 'index.html').is_file()
    result['javascript'] = (ROOT_DIR / 'api' / 'static' / 'app.js').is_file()
    result['lead_assets'] = all((ROOT_DIR / 'api' / 'static' / name).is_file()
                                for name in ('common.js', 'leads.html', 'leads.js', 'leads.css', 'workflow.html', 'workflow.js', 'source-example.json'))
    result['quinland_dataset'] = (ROOT_DIR / 'resources' / 'datasets' / 'quinland.json').is_file()
    result['registry'] = RegistryFilterEngine().evaluate('Cần mua 0912345678')['classification'] == 'LEAD_POTENTIAL'
    result['negated_purchase'] = RegistryFilterEngine().evaluate('xấu vcl nhìn k muốn mua')['classification'] == 'IGNORE'
    result['property_inquiries'] = (RegistryFilterEngine().evaluate('xin hướng nhà')['classification'] == 'NEEDS_REVIEW'
                                    and RegistryFilterEngine().evaluate('2 tỷ mua luôn')['classification'] == 'LEAD_POTENTIAL')
    result['context_and_strength'] = (RegistryFilterEngine().evaluate('dm')['interest_level'] == 'unclear'
                                    and RegistryFilterEngine().evaluate('DM me the price')['interest_level'] == 'moderate')
    result['comment_collection_timeout'] = FacebookCommentCollector(RUNTIME_DIR / 'timeout-check').timeout_seconds == 300
    engine = RegistryFilterEngine()
    result['imported_registry'] = (engine.version == '1.4.0'
        and engine.evaluate('Nhà này có dính quy hoạch không?')['classification'] == 'NEEDS_REVIEW'
        and not engine.evaluate('có hỗ trợ vay vốn không')['signals']['spam']
        and engine.evaluate('ké chủ tus bên em có căn tương tự 0912345678')['classification'] == 'IGNORE'
        and engine.evaluate('fix giá giá cuối bớt được không')['score'] == 30)
    workbook = openpyxl.load_workbook(BytesIO(comment_report_bytes(COMMENT_EXAMPLE)))
    result['excel'] = workbook.active.max_row == len(COMMENT_EXAMPLE) + 1
    # Construct the actual HTTPS context offline too: missing runtime SSL data
    # can break requests even while the dashboard and bundled browser work.
    import ssl
    import certifi
    tls = ssl.create_default_context(cafile=certifi.where())
    result['https_tls'] = tls.verify_mode == ssl.CERT_REQUIRED and tls.check_hostname
    workbook.close()
    with tempfile.TemporaryDirectory(prefix='exe-check-', dir=RUNTIME_DIR) as temporary:
        service = CampaignService(db_path=Path(temporary) / 'campaigns.sqlite3', recover_on_start=False)
        result['sqlite'] = service.list_campaigns() == []
        from services.website_source import WebsiteSourceService, clean_post_html
        from services.image_fetcher import is_cloudflare_block
        ws = WebsiteSourceService(Path(temporary) / 'sources')
        bulk = ws.import_json([{'content': f'Bài kiểm tra {i}', 'images': []} for i in range(35)])
        result['json_unrestricted'] = len(bulk) == 35 and is_cloudflare_block(403, {'server': 'cloudflare'})
        fast_ws = WebsiteSourceService(Path(temporary) / 'fast-sources')
        fast = fast_ws.import_json([{'content': f'Nạp nhanh {i}',
            'images': [f'https://images.example/{i}.jpg']} for i in range(35)], defer_images=True)
        catalog = fast_ws.listing_catalog(limit=10)
        result['html_post_cleaning'] = clean_post_html('<p>Nhà đẹp<br><br>72m² &amp; giá 20 tỷ</p>') == 'Nhà đẹp\n\n72m² & giá 20 tỷ'
        result['fast_json_catalog'] = (len(fast) == 35 and len(catalog['items']) == 10
            and catalog['total'] == 35 and all(row.pending_image_urls and not row.image_paths for row in fast))
        result['delete_sources'] = fast_ws.delete_listings([fast[0].id]) == 1 and fast_ws.delete_listings(delete_all=True) == 34
        with sync_playwright() as p:
            context = launch_context(p, Path(temporary) / 'profile', True)
            try:
                page = context.new_page()
                page.route('**/*', lambda route: route.abort())
                page.set_content('<title>Offline EXE check</title><p>Ready</p>')
                result['chromium'] = page.title() == 'Offline EXE check'
            finally:
                context.close()
    result['passed'] = all(value for key, value in result.items() if key != 'frozen')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


def bind_first_free_port(preferred, attempts=20):
    """Return a listening socket on the preferred port, or the next free one."""
    last_error = None
    for port in range(preferred, min(preferred + attempts, 65536)):
        listener = socket.socket()
        try:
            listener.bind(('127.0.0.1', port))
            listener.listen(128)
            return listener, port
        except OSError as exc:
            listener.close()
            last_error = exc
    raise ValueError(f'Không tìm được cổng trống từ {preferred} đến {preferred + attempts - 1}. '
                     'Hãy đóng bớt chương trình khác rồi mở lại.') from last_error


def running_dashboard_build(url):
    parts = urlsplit(url)
    connection = http.client.HTTPConnection('127.0.0.1', parts.port, timeout=2)
    try:
        connection.request('GET', '/api/app-info')
        response = connection.getresponse()
        if response.status != 200:
            return None
        payload = json.loads(response.read(4096))
        return payload.get('build_id') if isinstance(payload, dict) else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def reopen_running_dashboard(runtime, open_browser=True):
    """When this customer's tool is already running, just reopen its page."""
    try:
        url = (runtime / 'dashboard.url').read_text(encoding='utf-8').strip()
    except OSError:
        url = ''
    if not re.fullmatch(r'http://127\.0\.0\.1:\d{4,5}', url):
        return False
    if running_dashboard_build(url) != BUILD_ID:
        raise ValueError('Một phiên bản tool cũ hoặc chưa sẵn sàng đang chạy. '
                         'Hãy đóng cửa sổ chạy tool cũ (không chỉ tab trình duyệt), '
                         'sau đó mở lại CongCuBDS_JSON.exe.')
    print(f'\nTool đang chạy sẵn. Đang mở lại giao diện: {url}', flush=True)
    if open_browser:
        webbrowser.open(url)
    return True


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description='Facebook Property Tool — Windows')
    parser.add_argument('--customer', default='default', help='Tên bộ dữ liệu khách')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true', help='Không tự mở dashboard')
    parser.add_argument('--self-test', metavar='RESULT_JSON', help='Kiểm tra offline bản đóng gói')
    args = parser.parse_args()
    try:
        runtime = configure_runtime(args.customer)
        if not 1024 <= args.port <= 65535:
            raise ValueError('Cổng cần từ 1024 đến 65535.')
        if args.self_test:
            return offline_self_test(args.self_test)
        from filelock import FileLock, Timeout
        # Keep one dashboard owner for each customer's data, even on another port.
        lock = FileLock(str(runtime / 'dashboard.lock'))
        try:
            lock.acquire(timeout=0)
        except Timeout as exc:
            if reopen_running_dashboard(runtime, not args.no_browser):
                if getattr(sys, 'frozen', False) and not args.no_browser:
                    time.sleep(3)
                return 0
            raise ValueError('Tool đang chạy ở một cửa sổ khác. Hãy dùng cửa sổ đó hoặc đóng nó trước.') from exc
        url_file = runtime / 'dashboard.url'
        try:
            listener, port = bind_first_free_port(args.port)
            with listener:
                from api.server import app
                import uvicorn
                url = f'http://127.0.0.1:{port}'
                url_file.write_text(url, encoding='utf-8')
                print('\n' + '=' * 60)
                print('  CÔNG CỤ BĐS FACEBOOK ĐANG CHẠY')
                print('=' * 60)
                print(f'  Giao diện : {url}')
                print(f'  Dữ liệu   : {runtime}')
                if port != args.port:
                    print(f'  (Cổng {args.port} đang bận nên tool dùng cổng {port})')
                print('-' * 60)
                print('  • Trình duyệt sẽ tự mở. Nếu không, hãy mở địa chỉ ở trên.')
                print('  • KHÔNG đóng cửa sổ này khi đang dùng tool.')
                print('  • Muốn tắt tool: chờ đăng bài/lấy bình luận xong rồi đóng cửa sổ này.')
                print('=' * 60 + '\n', flush=True)
                server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                    loop='asyncio', http='h11', ws='none', log_level='warning'))
                if not args.no_browser:
                    def open_dashboard():
                        while not server.started and not server.should_exit:
                            time.sleep(0.1)
                        if server.started:
                            webbrowser.open(url)
                    threading.Thread(target=open_dashboard, daemon=True).start()
                server.run(sockets=[listener])
        finally:
            try:
                url_file.unlink(missing_ok=True)
            finally:
                lock.release()
        return 0
    except Exception as exc:
        print(f'\nKhông khởi động được tool: {exc}', file=sys.stderr)
        logging.exception('Desktop startup failed')
        if getattr(sys, 'frozen', False) and not args.no_browser and not args.self_test:
            input('Nhấn Enter để đóng...')
        return 1


if __name__ == '__main__':
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
