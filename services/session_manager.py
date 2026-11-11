"""Interactive Facebook login. One browser owner per customer profile."""
from pathlib import Path
import shutil
import threading
import time
from playwright.sync_api import sync_playwright
from config.settings import PROFILE_DIR
from models.schema import SessionStatus
from services.facebook_browser import authenticated, launch_context, profile_operation
from services.storage import ResourceBusyError


class FacebookSessionManager:
    def __init__(self, profile_dir=None):
        self.profile_dir = Path(profile_dir or PROFILE_DIR)
        self._login_lock = threading.Lock()
        self._login_result = None
        # Last verified state (from a real check or a finished login). Used by
        # quick_status() so the UI can show a badge without opening Chromium.
        self._last_valid = None

    def _status(self, valid=False, message='', busy=False):
        return SessionStatus(is_authenticated=valid, status_text=message,
                             profile_dir=str(self.profile_dir), busy=busy,
                             login_in_progress=self._login_lock.locked(), login_result=self._login_result)

    def _has_profile(self):
        try:
            return self.profile_dir.exists() and any(self.profile_dir.iterdir())
        except OSError:
            return False

    def quick_status(self):
        """Cheap status for the dashboard badge. Never launches a browser."""
        if self._login_lock.locked():
            return self._status(message='Đang chờ bạn đăng nhập trên cửa sổ Facebook...', busy=True)
        if self._last_valid is True:
            return self._status(True, 'Đã kết nối Facebook')
        if self._last_valid is False:
            return self._status(False, 'Cần đăng nhập lại Facebook')
        if self._has_profile():
            return self._status(False, 'Có phiên đã lưu — bấm “Kiểm tra” để xác nhận')
        return self._status(False, 'Chưa đăng nhập Facebook')

    def check_session_status(self):
        if self._login_lock.locked():
            return self._status(message='Đang chờ khách hoàn tất đăng nhập trên cửa sổ Facebook.', busy=True)
        try:
            with profile_operation(self.profile_dir):
                if not self._has_profile():
                    self._last_valid = None
                    return self._status(message='Chưa đăng nhập Facebook. Bấm “Đăng nhập Facebook”.')
                with sync_playwright() as p:
                    context = launch_context(p, self.profile_dir, True)
                    try:
                        page = context.new_page()
                        page.goto('https://www.facebook.com/', wait_until='domcontentloaded', timeout=30000)
                        page.wait_for_timeout(1500)
                        valid = authenticated(page, context)
                        self._last_valid = valid
                        return self._status(valid, 'Đã kết nối Facebook' if valid else 'Cần đăng nhập lại hoặc hoàn tất xác minh Facebook')
                    finally:
                        context.close()
        except ResourceBusyError:
            return self._status(message='Trình duyệt đang được sử dụng. Hãy chờ thao tác hiện tại hoàn tất.', busy=True)
        except Exception:
            return self._status(message='Không kiểm tra được phiên. Kiểm tra mạng và cài Chromium (xem README).')

    def start_login(self, timeout_seconds=180):
        if not self._login_lock.acquire(blocking=False):
            raise ResourceBusyError('Cửa sổ đăng nhập đang mở.')
        self._login_result = None
        def worker():
            try:
                self._login_result = self._interactive(timeout_seconds)
                if self._login_result.get('success'):
                    self._last_valid = True
            finally:
                self._login_lock.release()
        threading.Thread(target=worker, daemon=True, name='facebook-login').start()

    def open_interactive_login(self, timeout_seconds=180):
        if not self._login_lock.acquire(blocking=False):
            raise ResourceBusyError('Cửa sổ đăng nhập đang mở.')
        try:
            self._login_result = self._interactive(timeout_seconds)
            return self._login_result
        finally:
            self._login_lock.release()

    def _interactive(self, timeout_seconds):
        try:
            with profile_operation(self.profile_dir), sync_playwright() as p:
                context = launch_context(p, self.profile_dir, False)
                try:
                    page = context.new_page()
                    page.goto('https://www.facebook.com/', timeout=60000)
                    deadline = time.monotonic() + timeout_seconds
                    while time.monotonic() < deadline:
                        if authenticated(page, context):
                            return {'success': True, 'message': 'Đã xác nhận đăng nhập và lưu phiên.'}
                        page.wait_for_timeout(1000)
                    return {'success': False, 'message': 'Hết thời gian chờ. Hãy mở lại để hoàn tất đăng nhập/xác minh.'}
                finally:
                    context.close()
        except ResourceBusyError as exc:
            return {'success': False, 'message': str(exc)}
        except Exception:
            return {'success': False, 'message': 'Không mở được phiên. Kiểm tra Chromium, mạng hoặc cửa sổ đã bị đóng.'}

    def logout_and_clear_session(self):
        if self._login_lock.locked():
            raise ResourceBusyError('Hãy đóng hoặc hoàn tất đăng nhập trước khi xóa phiên.')
        with profile_operation(self.profile_dir):
            if self.profile_dir.exists():
                shutil.rmtree(self.profile_dir)
            if self.profile_dir.exists():
                raise RuntimeError('Chưa xóa được toàn bộ phiên Facebook.')
            self._last_valid = None
            self._login_result = None
            return {'success': True, 'message': 'Đã xóa dữ liệu phiên trên máy. Có thể thu hồi phiên từ Facebook > Mật khẩu và bảo mật.'}
