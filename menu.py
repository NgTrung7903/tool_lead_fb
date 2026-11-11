"""Interactive launcher. No Facebook action runs until selected by the user."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


class ToolMenu:
    def __init__(self, customer='khach01', port=8000, ask=input, say=print):
        self.ask, self.say = ask, say
        self.set_customer(customer)
        self.port = port
        self.python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    def set_customer(self, name):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', name):
            raise ValueError('Tên khách: chữ/số/gạch ngang/gạch dưới, tối đa 48 ký tự.')
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        self.customer = name
        self.data_dir = base / 'RevolandFBPoster' / name

    def prompt(self, label, default=None):
        value = self.ask(label + (f' [{default}]' if default is not None else '') + ': ').strip()
        return (value or str(default or '')).strip('"')

    def choose(self, title, choices):
        self.say('\n' + title)
        for key, label in choices.items(): self.say(f'  {key}. {label}')
        return self.prompt('Chọn số')

    def run_process(self, arguments, python=True):
        command = ([str(self.python)] if python else []) + [str(a) for a in arguments]
        environment = dict(os.environ)
        # Every child uses the selected customer, including existing Page tests.
        environment['REVOLAND_DATA_DIR'] = str(self.data_dir)
        environment['PYTHONUTF8'] = '1'
        process = subprocess.Popen(command, cwd=ROOT, env=environment, shell=False)
        try:
            code = process.wait()
        except KeyboardInterrupt:
            self.say('\nĐang chờ tác vụ dừng để trở về menu...')
            try:
                code = process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                # Stop only the child process tree started by this menu.
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    process.terminate()
                process.wait(timeout=10)
                code = 130
        if code not in (0, 130): self.say(f'Lệnh kết thúc với mã {code}. Xem thông báo lỗi phía trên.')
        return code

    def cli(self, *args):
        return self.run_process(['cli.py', *args])

    def dashboard(self):
        self.say('Dashboard tự mở trong trình duyệt. Giữ terminal này khi dùng.')
        self.say('Chờ tác vụ đăng xong; Ctrl+C dừng server và trở về menu.')
        return self.run_process(['desktop_launcher.py', '--customer', self.customer, '--port', self.port])

    def facebook(self):
        choice = self.choose('PHIÊN FACEBOOK', {'1':'Đăng nhập (chờ tối đa 10 phút)',
            '2':'Kiểm tra phiên', '3':'Giữ cửa sổ mở để tự kiểm tra/chuyển tài khoản',
            '4':'Đăng xuất / xóa phiên', '0':'Quay lại'})
        if choice == '1': self.cli('--login-fb', '--login-timeout', '600')
        elif choice == '2': self.cli('--check-session')
        elif choice == '3':
            url = self.prompt('URL Trang Facebook có ID (để trống để hủy)')
            if url: self.cli('--page-session', '--page-url', url, '--login-timeout', '600')
        elif choice == '4':
            if self.prompt('Gõ XOA để xóa phiên Facebook của khách đang chọn') == 'XOA':
                self.cli('--logout-fb')

    def show_functions(self):
        self.say(f'''
Mở chức năng trên dashboard (chọn 1 ở menu chính để khởi động):
  http://127.0.0.1:{self.port}/          Lấy tin JSON/JSON-LD, demo, ảnh, nhóm,
                                        duyệt nội dung, đăng/retry/xác minh,
                                        chuyển bài đã đăng sang lọc lead.
  http://127.0.0.1:{self.port}/leads     Lấy/dừng bình luận, lịch sử, lọc ba mức,
                                        dán/nhập JSON bình luận, registry, Excel.
  http://127.0.0.1:{self.port}/posting   Cấu hình API Revoland, chọn căn/nhóm,
                                        preview, đăng và lịch sử cũ.
  http://127.0.0.1:{self.port}/docs      Danh sách API để người phát triển thử.
Các trang này dùng chung một server. Không cần chạy từng function Python.
Đăng Trang kiểm thử bằng file QuinLand hiện nằm ở mục 4, chưa nối dashboard.
''')

    def page_runs(self):
        folder = self.data_dir / 'data' / 'page_tests'
        runs = []
        for path in folder.glob('*/run.json'):
            row = json.loads(path.read_text(encoding='utf-8'))
            if re.fullmatch(r'[a-f0-9]{32}', str(row.get('id', ''))): runs.append(row)
        return sorted(runs, key=lambda r:r.get('created_at', ''), reverse=True)

    def select_page_run(self):
        runs = self.page_runs()
        if not runs:
            self.say('Chưa có bài kiểm thử của khách này. Chuẩn bị bài mới hoặc chọn đúng khách.')
            return None
        for index, row in enumerate(runs, 1):
            self.say(f"  {index}. {row['id']} | {row.get('status')} | {row.get('page_name')} | {row.get('created_at')}")
        number = self.prompt('Chọn bài bằng số, 0 để quay lại')
        if number == '0': return None
        if not number.isdigit() or not 1 <= int(number) <= len(runs):
            raise ValueError('Số bài không hợp lệ.')
        return runs[int(number)-1]

    def page_test(self):
        choice = self.choose('KIỂM THỬ ĐĂNG TRANG — mã nguồn, chưa nghiệm thu thành công trên Trang thật',
            {'1':'Chuẩn bị 1 bài từ file QuinLand (chưa đăng)', '2':'Xem bài đã chuẩn bị và kết quả',
             '3':'Gửi 1 bài đã duyệt lên Trang thật', '0':'Quay lại'})
        if choice == '1':
            filename = self.prompt('Đường dẫn file JSON QuinLand (để trống để hủy)')
            if not filename: return
            if not Path(filename).is_file(): raise ValueError('Không tìm thấy file JSON.')
            url = self.prompt('URL Trang Facebook')
            name = self.prompt('Tên Trang cần khớp danh tính người đăng')
            if not url or not name: raise ValueError('Cần URL và tên Trang.')
            self.cli('--page-test', '--source-json', filename, '--page-url', url, '--page-name', name)
        elif choice in ('2', '3'):
            row = self.select_page_run()
            if row is None: return
            self.say(f"\nTrang: {row.get('page_name')}\nURL: {row.get('page_url')}\nTrạng thái: {row.get('status')}")
            self.say(row.get('content', ''))
            self.say(f"Số ảnh: {len(row.get('images', []))}")
            if row.get('message'): self.say(row['message'])
            if row.get('post_url'): self.say('Link kết quả: ' + row['post_url'])
            if choice == '3':
                if row.get('submission_started') or row.get('status') in ('posted', 'unknown', 'running', 'submitting'):
                    self.say('Đã bắt đầu gửi hoặc chưa rõ kết quả. Kiểm tra Facebook; không gửi lại từ menu.')
                    return
                if self.prompt('Lệnh này đăng THẬT nội dung/ảnh trên. Gõ DANG để thực hiện') == 'DANG':
                    self.cli('--page-test', '--page-run', row['id'], '--submit-page-test')

    def reports(self):
        choice = self.choose('XUẤT EXCEL', {'1':'Toàn bộ lịch sử đăng nhóm', '2':'Một chiến dịch đăng nhóm',
            '3':'Lọc bình luận/lead từ file JSON rồi xuất Excel', '0':'Quay lại'})
        args = []
        if choice == '1': args = ['--export-posts']
        elif choice == '2':
            campaign = self.prompt('Mã chiến dịch')
            if campaign: args = ['--export-posts', '--campaign', campaign]
        elif choice == '3':
            filename = self.prompt('File JSON bình luận (không phải file tin BĐS)')
            if filename: args = ['--export-comments', filename]
        if args:
            output = self.prompt('File .xlsx đích; để trống dùng tên tự tạo trong dữ liệu khách')
            if output: args += ['--output', output]
            self.cli(*args)

    def legacy(self):
        choice = self.choose('CLI REVOLAND / ĐĂNG NHÓM', {'1':'Xem danh sách căn Revoland',
            '2':'Xem danh sách nhóm đã lưu', '3':'Đăng 1 căn Revoland vào nhóm',
            '4':'Thử lại nhóm lỗi của một chiến dịch', '0':'Quay lại'})
        if choice == '1': self.cli('--list-listings')
        elif choice == '2': self.cli('--list-groups')
        elif choice == '3':
            listing = self.prompt('ID căn')
            groups = self.prompt('ID nhóm, phân tách bằng dấu phẩy')
            if not listing or not groups: raise ValueError('Cần ID căn và ít nhất một ID nhóm.')
            self.say(f'Căn: {listing}; nhóm: {groups}. Lệnh này sẽ gửi Facebook thật nếu đủ điều kiện.')
            if self.prompt('Gõ DANG để tạo và chạy chiến dịch') == 'DANG':
                self.cli('--post', '--listing', listing, '--groups', groups)
        elif choice == '4':
            campaign = self.prompt('Mã chiến dịch')
            if campaign and self.prompt('Thử lại có thể gửi bài thật. Gõ THULAI để chạy') == 'THULAI':
                self.cli('--retry', campaign)

    def development(self):
        choice = self.choose('KIỂM THỬ / BUILD', {'1':'Chạy toàn bộ test offline',
            '2':'Chạy test đăng Trang offline', '3':'Build lại EXE', '4':'Kiểm tra EXE bằng demo offline',
            '5':'Cài/cập nhật dependency và Chromium', '0':'Quay lại'})
        if choice == '1': self.run_process(['-m', 'pytest', '-q'])
        elif choice == '2': self.run_process(['-m', 'pytest', '-q', 'tests/test_page_post.py'])
        elif choice == '3':
            self.say('Dừng EXE cũ trước khi build. Tác vụ có thể mất vài phút.')
            self.run_process(['powershell.exe', '-NoProfile', '-File', str(ROOT/'build_exe.ps1')], python=False)
        elif choice == '4': self.run_process(['packaging/verify_exe.py'])
        elif choice == '5':
            if self.run_process(['-m', 'pip', 'install', '-r', 'requirements-lock.txt']) == 0:
                self.run_process(['-m', 'playwright', 'install', 'chromium'])

    def run(self):
        choices = {'1':'Mở toàn bộ giao diện tool', '2':'Đăng nhập / kiểm tra / chuyển tài khoản Facebook',
            '3':'Xem chức năng và địa chỉ các trang', '4':'Kiểm thử đăng Trang từ JSON QuinLand',
            '5':'Xuất Excel', '6':'Lệnh Revoland / đăng nhóm / retry', '7':'Kiểm thử / build / cài dependency',
            '8':'Đổi khách và cổng', '9':'Xem trợ giúp CLI', '0':'Thoát'}
        while True:
            self.say(f'\nFACEBOOK PROPERTY TOOL | Khách: {self.customer} | Cổng: {self.port}\nDữ liệu: {self.data_dir}')
            try:
                choice = self.choose('MENU CHÍNH', choices)
                if choice == '0': return
                if choice == '1': self.dashboard()
                elif choice == '2': self.facebook()
                elif choice == '3': self.show_functions()
                elif choice == '4': self.page_test()
                elif choice == '5': self.reports()
                elif choice == '6': self.legacy()
                elif choice == '7': self.development()
                elif choice == '8':
                    name = self.prompt('Tên khách (page-test là phiên kiểm thử Trang đã dùng)', self.customer)
                    port = int(self.prompt('Cổng', self.port))
                    if not 1024 <= port <= 65535: raise ValueError('Cổng từ 1024 đến 65535.')
                    self.set_customer(name)
                    self.port = port
                elif choice == '9': self.cli('--help')
                else: self.say('Chọn một số trong menu.')
            except (EOFError, KeyboardInterrupt):
                self.say('\nĐã thoát menu.')
                return
            except (ValueError, OSError) as exc:
                self.say('Không thực hiện được: ' + str(exc))


def main():
    if sys.stdout is not None: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='Menu điều khiển Facebook Property Tool')
    parser.add_argument('--customer', default='khach01')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('Cổng từ 1024 đến 65535.')
    try:
        menu = ToolMenu(args.customer, args.port)
    except ValueError as exc:
        parser.error(str(exc))
    if not menu.python.is_file():
        parser.error('Chưa có .venv. Cài môi trường theo docs/USER_GUIDE.md trước.')
    menu.run()


if __name__ == '__main__':
    main()
