"""Explicit, durable one-post Page test through the project's Playwright runtime.

This is separate from the group campaign UI. Archived source records remain
archived and are only quoted in an unmistakable test post.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

from config.settings import RUNTIME_DIR, PROFILE_DIR
from models.schema import utc_now_iso
from services.facebook_browser import authenticated, launch_context, profile_operation
from services.poster_engine import normalize_text
from services.storage import ExclusiveOperation, ResourceBusyError, atomic_json
from services.website_source import fetch_public


def open_page_session(url, timeout=600):
    _, target = page_identity(url)
    with profile_operation(PROFILE_DIR), sync_playwright() as playwright:
        context = launch_context(playwright, PROFILE_DIR, False)
        try:
            page = context.new_page()
            page.goto(target, wait_until='domcontentloaded', timeout=45000)
            print('Cửa sổ giữ mở để bạn tự kiểm tra/chuyển tài khoản. Khi xong hãy đóng cửa sổ Chromium.', flush=True)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and context.pages:
                try:
                    context.pages[0].wait_for_timeout(1000)
                except Exception:
                    break
        finally:
            context.close()
    print('Đã đóng cửa sổ. Chưa gửi bài trong chế độ kiểm tra phiên.', flush=True)


def page_identity(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com') or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Cần URL HTTPS Trang Facebook có ID.')
    match = re.fullmatch(r'/people/[^/]+/(\d+)/?', parts.path)
    identifier = match.group(1) if match else parse_qs(parts.query).get('id', [''])[0] if parts.path == '/profile.php' else ''
    if not re.fullmatch(r'\d+', identifier):
        raise ValueError('Chỉ nhận /people/TEN/ID hoặc /profile.php?id=ID trong bản kiểm thử Trang.')
    return identifier, 'https://www.facebook.com/profile.php?id=' + identifier


def page_permalink(url, page_id):
    parts = urlsplit(url)
    if parts.hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
        return None
    query = parse_qs(parts.query)
    story = query.get('story_fbid', [''])[0]
    if parts.path == '/permalink.php' and query.get('id') == [page_id] and re.fullmatch(r'[A-Za-z0-9]+', story):
        return f'https://www.facebook.com/permalink.php?story_fbid={story}&id={page_id}'
    if re.fullmatch('/' + re.escape(page_id) + r'/posts/[A-Za-z0-9]+/?', parts.path):
        return 'https://www.facebook.com' + parts.path.rstrip('/')
    return None


class FacebookPagePoster:
    def __init__(self, profile_dir=None):
        self.profile_dir = Path(profile_dir or PROFILE_DIR)
        self.upload_timeout = 90
        self.confirmation_timeout = 45

    def publish(self, run, before_submit, proof_dir):
        sent = False
        page_id, target = page_identity(run['page_url'])
        content = run['content']
        paths = [row['path'] for row in run['images']]
        outcome = {'status': 'failed', 'submission_started': False}
        try:
            with profile_operation(self.profile_dir), sync_playwright() as playwright:
                context = launch_context(playwright, self.profile_dir, False)
                try:
                    page = context.new_page()
                    page.set_default_timeout(12000)
                    page.goto(target, wait_until='domcontentloaded', timeout=45000)
                    page.wait_for_timeout(2500)
                    if not authenticated(page, context):
                        return {'status': 'action_required', 'message': 'Cần đăng nhập bằng cửa sổ của project.', 'submission_started': False}
                    switch = page.get_by_role('button', name=re.compile(r'^(Chuyển ngay|Switch now)$', re.I))
                    if switch.count() and switch.first.is_visible():
                        switch.first.click()
                        page.wait_for_timeout(2500)
                    opener = page.get_by_role('button', name=re.compile(r'^(Bạn đang nghĩ gì\??|What.s on your mind.*|Create post|Tạo bài viết)$', re.I))
                    opener.first.click()
                    dialog = page.get_by_role('dialog').filter(has=page.locator('[contenteditable="true"]')).last
                    dialog.wait_for(state='visible')
                    if not dialog.get_by_text(run['page_name'], exact=True).count():
                        return {'status': 'action_required', 'message': 'Danh tính soạn bài không khớp Trang yêu cầu; chưa nhập/gửi nội dung.', 'submission_started': False}
                    editor = dialog.locator('[role="textbox"][contenteditable="true"]').first
                    editor.fill(content)
                    # A pre-existing photo draft must not be silently republished.
                    if dialog.get_by_role('button', name=re.compile(r'(Gỡ file đính kèm|Remove attachments|Remove photo)', re.I)).count():
                        raise ValueError('Ô soạn đang có file từ bản nháp cũ. Chưa gửi.')
                    if paths:
                        with page.expect_file_chooser(timeout=15000) as chooser:
                            dialog.get_by_role('button', name=re.compile(r'^(Ảnh\/video|Photo\/video)$', re.I)).click()
                        chooser.value.set_files(paths)
                        deadline = time.monotonic() + self.upload_timeout
                        while time.monotonic() < deadline:
                            ready = all(dialog.get_by_role('img', name=Path(path).name, exact=True).count() == 1 and
                                dialog.get_by_role('img', name=Path(path).name, exact=True).evaluate(
                                    'e => e.complete && e.naturalWidth > 0 && !!e.getClientRects().length') for path in paths)
                            next_button = dialog.get_by_role('button', name=re.compile(r'^(Tiếp|Next|Đăng|Post)$'))
                            if ready and next_button.count() and next_button.last.is_enabled() and not dialog.locator('[role="progressbar"]:visible').count():
                                break
                            page.wait_for_timeout(500)
                        else:
                            raise ValueError('Chưa xác nhận tải đủ ảnh; chưa gửi.')
                    # Facebook may reset part of the editor while attaching photos.
                    editor.fill(content)
                    if normalize_text(editor.inner_text()) != normalize_text(content):
                        raise ValueError('Ô soạn không khớp nội dung đã duyệt; chưa gửi.')
                    next_button = dialog.get_by_role('button', name=re.compile(r'^(Tiếp|Next)$'))
                    if next_button.count():
                        next_button.click()
                        dialog = page.get_by_role('dialog').last
                        dialog.get_by_role('button', name=re.compile(r'^(Đăng|Post)$')).wait_for(state='visible')
                    if normalize_text(content) not in normalize_text(dialog.inner_text()):
                        raise ValueError('Bản xem trước cuối không đủ nội dung; chưa gửi.')
                    if any(s.get_attribute('aria-checked') == 'true' for s in dialog.get_by_role('switch').all()):
                        raise ValueError('Có tùy chọn bật trong bước xuất bản; kiểm tra quảng bá/lịch đăng trước. Chưa gửi.')
                    submit = dialog.get_by_role('button', name=re.compile(r'^(Đăng|Post)$')).last
                    if not submit.is_enabled():
                        raise ValueError('Facebook chưa cho gửi bài.')
                    proof_dir = Path(proof_dir)
                    page.screenshot(path=str(proof_dir / 'before_submit.png'))
                    before_submit()
                    sent = True
                    submit.click(timeout=15000)
                    deadline = time.monotonic() + self.confirmation_timeout
                    first_line = content.splitlines()[0]
                    while time.monotonic() < deadline:
                        if not authenticated(page, context):
                            break
                        markers = page.get_by_text(first_line, exact=False)
                        marker = next((item for item in markers.all() if item.is_visible()), None)
                        if marker is not None and not page.get_by_role('button', name=re.compile(r'^(Đăng|Post)$')).count():
                            scope = marker
                            for _ in range(15):
                                scope = scope.locator('..')
                                expand = scope.get_by_role('button', name=re.compile(r'^(Xem thêm|See more)$', re.I))
                                if expand.count() and normalize_text(content) not in normalize_text(scope.inner_text()):
                                    expand.first.click()
                                if normalize_text(content) not in normalize_text(scope.inner_text()):
                                    continue
                                fresh = scope.get_by_role('link', name=re.compile(r'^(Vừa xong|Just now)$', re.I))
                                if fresh.count():
                                    fresh.first.click()
                                    page.wait_for_timeout(1500)
                                    permalink = page_permalink(page.url, page_id)
                                    if permalink and normalize_text(content) in normalize_text(page.locator('body').inner_text()):
                                        photo_count = page.locator('a[href*="/photo/"]').count()
                                        if photo_count < len(paths):
                                            break
                                        page.screenshot(path=str(proof_dir / 'posted.png'))
                                        return {'status': 'posted', 'submission_started': True, 'post_url': permalink,
                                            'evidence': 'project_playwright_fresh_permalink_full_content_photos',
                                            'visible_photo_links': photo_count, 'posted_at': utc_now_iso()}
                                    break
                        page.wait_for_timeout(1000)
                    outcome = {'status': 'unknown', 'submission_started': True,
                        'message': 'Đã gửi nhưng chưa đủ bằng chứng permalink/nội dung/ảnh. Không tự đăng lại.'}
                except Exception as exc:
                    outcome = {'status': 'unknown' if sent else 'failed', 'submission_started': sent,
                               'message': f'{type(exc).__name__}: {str(exc)[:600]}'}
                    try:
                        page.screenshot(path=str(Path(proof_dir) / 'failure.png'))
                    except Exception:
                        pass
                finally:
                    context.close()
        except ResourceBusyError as exc:
            outcome = {'status': 'action_required', 'message': str(exc), 'submission_started': False}
        return outcome


class PagePostService:
    def __init__(self, root=None, poster=None):
        self.root = Path(root or RUNTIME_DIR / 'data' / 'page_tests')
        self.root.mkdir(parents=True, exist_ok=True)
        self.poster = poster or FacebookPagePoster()

    def _path(self, run_id):
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise ValueError('Mã bài kiểm thử không hợp lệ.')
        return self.root / run_id / 'run.json'

    def get(self, run_id):
        return json.loads(self._path(run_id).read_text(encoding='utf-8'))

    def prepare(self, source_file, page_url, page_name):
        page_id, page_url = page_identity(page_url)
        if not page_name.strip():
            raise ValueError('Cần tên Trang để kiểm tra danh tính người đăng.')
        raw = Path(source_file).read_bytes()
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('File vượt 10 MB.')
        rows = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise ValueError('Cần mảng dữ liệu QuinLand không trống.')
        row = rows[0]
        if row.get('isDeleted'):
            raise ValueError('Không dùng bản ghi đã đánh dấu xóa.')
        identifier = uuid.uuid4().hex
        folder = self.root / identifier
        folder.mkdir()
        details = row.get('propertyDetails') or {}
        price = row.get('priceDetails') or {}
        content = '\n'.join([
            f'KIỂM THỬ TOOL FACEBOOK — {identifier[:8]}', '',
            'Bài này được gửi bằng code Playwright của project để kiểm thử nội dung và ảnh.', '',
            str(row.get('title') or 'Tin bất động sản được cung cấp').strip(),
            *([f"Diện tích theo dữ liệu: {details['buildingArea']} m²"] if details.get('buildingArea') else []),
            *([f"Giá trong dữ liệu: {price['salePrice']:,} VND"] if isinstance(price.get('salePrice'), int) else []),
            '', f"Trạng thái nguồn: {row.get('status', 'chưa xác định')}.",
            'Đây là bài kiểm thử; không xác nhận căn đang bán hoặc giá còn hiệu lực.',
            'Không dùng bài này thay cho tư vấn hoặc xác minh thông tin giao dịch.', '', '#KiemThuTool #BatDongSan'])
        run = {'id': identifier, 'status': 'prepared', 'page_url': page_url, 'page_id': page_id,
               'page_name': page_name.strip(), 'content': content, 'created_at': utc_now_iso(),
               'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_count': len(rows),
               'source_record_index': 0, 'source_status': row.get('status'), 'images': [], 'submission_started': False}
        images = row.get('images') or []
        if not isinstance(images, list) or any(not isinstance(url, str) for url in images):
            raise ValueError('images cần là mảng URL.')
        for index, url in enumerate(images[:4]):
            payload, _, _ = fetch_public(url, 20 * 1024 * 1024)
            path = folder / f'tool_{identifier[:8]}_{index+1}.jpg'
            with Image.open(io.BytesIO(payload)) as image:
                if image.width * image.height > 25000000:
                    raise ValueError('Ảnh vượt 25 megapixel.')
                ImageOps.exif_transpose(image).convert('RGB').save(path, 'JPEG', quality=95)
            run['images'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        atomic_json(folder / 'run.json', run)
        (folder / 'content.txt').write_text(content, encoding='utf-8')
        return run

    def submit(self, run_id):
        path = self._path(run_id)
        with ExclusiveOperation(path.parent / 'run.lock'):
            run = self.get(run_id)
            if run.get('submission_started') or run['status'] in ('posted', 'unknown', 'running'):
                raise ValueError('Lần này đã gửi hoặc chưa rõ kết quả; không tự gửi lại. Kiểm tra permalink/lịch sử.')
            for image in run['images']:
                if hashlib.sha256(Path(image['path']).read_bytes()).hexdigest() != image['sha256']:
                    raise ValueError('Ảnh đã thay đổi sau bước chuẩn bị; chưa gửi.')
            run.update(status='running', started_at=utc_now_iso())
            atomic_json(path, run)
            def before_submit():
                run.update(status='submitting', submission_started=True)
                atomic_json(path, run)
            try:
                result = self.poster.publish(run, before_submit, path.parent)
                run.update(result)
            except Exception as exc:
                run.update(status='unknown' if run['submission_started'] else 'failed', message=f'{type(exc).__name__}: {exc}')
            run['finished_at'] = utc_now_iso()
            atomic_json(path, run)
            return run
