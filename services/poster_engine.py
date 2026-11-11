"""Submit conservatively: no simulation, no success without evidence."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
import re
import time
import logging
from urllib.parse import parse_qs, urljoin, urlsplit
from playwright.sync_api import sync_playwright
from config.settings import PROFILE_DIR, load_config
from models.schema import GroupPostStatusEnum as Status, GroupTaskResult, utc_now_iso
from services.facebook_browser import authenticated, launch_context, profile_operation
from services.storage import ResourceBusyError

_INVISIBLE_CHARS_RE = re.compile(r'[\u200b-\u200f\u202a-\u202e\u2060-\u206f\u034f\ufeff\ufe0e\ufe0f]')
_PENDING_NOTICE_RE = re.compile(
    r'(bài viết của bạn.*(đang chờ|chờ phê duyệt|gửi tới quản trị viên)'
    r'|đang chờ phê duyệt'
    r'|\d+\s*bài viết đang chờ'
    r'|quản trị viên phê duyệt'
    r'|your post.*(pending|awaiting|submitted).*(approval|admin)'
    r'|\d+\s*posts?\s+pending\s+approval)',
    re.I | re.S,
)


def _group_paths(group_url, current_url=''):
    paths = []
    for raw in (group_url, current_url):
        if not raw:
            continue
        p = urlsplit(raw).path.rstrip('/')
        m = re.match(r'^(/groups/[^/]+)', p)
        if m and m.group(1) not in paths:
            paths.append(m.group(1))
    return paths or [urlsplit(group_url).path.rstrip('/')]


def post_permalink(value, group_url, current_url=''):
    if not value:
        return None
    cleaned = value.replace('\\/', '/')
    url = urlsplit(urljoin(current_url or group_url, cleaned))
    if url.hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
        return None
    group_paths = _group_paths(group_url, current_url)
    for gpath in group_paths:
        if re.fullmatch(re.escape(gpath) + r'/(posts|permalink)/[A-Za-z0-9._-]+/?', url.path):
            return 'https://www.facebook.com' + url.path.rstrip('/')
    if url.path.rstrip('/') == '/photo':
        set_param = parse_qs(url.query).get('set', [''])[0]
        m = re.match(r'^(?:pcb|gm)\.([0-9]+)$', set_param)
        if m and group_paths:
            return f'https://www.facebook.com{group_paths[0]}/posts/{m.group(1)}'
    return None


def normalize_text(text):
    cleaned = _INVISIBLE_CHARS_RE.sub('', text or '')
    return ' '.join(cleaned.split())


def compact_text(text):
    """Strip emojis, punctuation, invisible joiners and whitespace while keeping all letters/digits in order."""
    cleaned = _INVISIBLE_CHARS_RE.sub('', text or '')
    return re.sub(r'[^\w]+', '', cleaned, flags=re.UNICODE).lower()


def text_contains_approved_content(container_text: str, approved_content: str) -> bool:
    norm_expected = normalize_text(approved_content)
    if not norm_expected:
        return False
    norm_actual = normalize_text(container_text)
    if norm_expected in norm_actual:
        return True
    comp_expected = compact_text(approved_content)
    if len(comp_expected) >= 6:
        return comp_expected in compact_text(container_text)
    return False


def _prefix_matches_content(container_text: str, approved_content: str) -> bool:
    first_line = next((normalize_text(line) for line in approved_content.splitlines() if normalize_text(line)), '')
    if first_line and first_line in normalize_text(container_text):
        return True
    comp_first = compact_text(first_line or approved_content)[:28]
    if len(comp_first) >= 4 and comp_first in compact_text(container_text):
        return True
    return text_contains_approved_content(container_text, approved_content)


def collect_feed_permalinks(page, group_url):
    current = page.url
    found = set()
    for a in page.locator('a[href]').all():
        try:
            url = post_permalink(a.get_attribute('href') or '', group_url, current)
            if url:
                found.add(url)
        except Exception:
            continue
    return found


def _relay_permalinks_on_page(page, group_url):
    """Extract canonical group post URLs embedded in Facebook Relay JSON payloads on the current page."""
    try:
        html = page.content()
    except Exception:
        return []
    current = page.url
    found = []
    for raw_url in re.findall(r'https?:\\/\\/www\.facebook\.com\\/groups\\/[^"\'\s<>]+', html):
        url = post_permalink(raw_url, group_url, current)
        if url and url not in found:
            found.append(url)
    gpaths = _group_paths(group_url, current)
    if gpaths:
        for post_id in re.findall(r'"post_id"\s*:\s*"(\d{8,})"', html):
            url = f'https://www.facebook.com{gpaths[0]}/posts/{post_id}'
            if url not in found:
                found.append(url)
    return found


def confirmed_post(page, content, group_url, previous_links):
    """Require full approved text and a fresh permalink in the same feed post."""
    current = page.url
    candidates = []
    for loc in (page.locator('[role="article"]'), page.locator('[role="feed"] > div')):
        try:
            candidates.extend(loc.all())
        except Exception:
            pass

    matched_visible_container = False
    for container in candidates:
        try:
            if not container.is_visible():
                continue
            raw_text = container.inner_text()
            if not _prefix_matches_content(raw_text, content):
                continue
            if not text_contains_approved_content(raw_text, content):
                expand = container.get_by_role('button', name=re.compile(r'^(Xem thêm|See more)$', re.I))
                if expand.count() and expand.first.is_visible():
                    expand.first.click(timeout=2000)
                    page.wait_for_timeout(350)
                    raw_text = container.inner_text()
            if not text_contains_approved_content(raw_text, content):
                continue

            matched_visible_container = True
            for link in container.locator('a[href]').all():
                href = link.get_attribute('href') or ''
                url = post_permalink(href, group_url, current)
                if not url or url in previous_links:
                    continue
                timestamp = (link.inner_text() + ' ' + (link.get_attribute('aria-label') or '')).strip()
                if re.search(r'\b(just now|vừa xong|1\s*phút|1\s*m)\b', timestamp, re.I) or '/posts/' in url or '/permalink/' in url:
                    return url
        except Exception:
            continue

    # Text-only Facebook Comet posts may keep DOM timestamp links as ?__cft__ while embedding the post_id in Relay JSON.
    if matched_visible_container:
        for url in _relay_permalinks_on_page(page, group_url):
            if url not in previous_links:
                return url
    return None


class _GraphQLSubmitMonitor:
    """Passively captures post permalink / moderation state from Facebook's GraphQL story_create response."""
    def __init__(self, page, group_url: str, previous_links: set[str]):
        self.page = page
        self.group_url = group_url
        self.previous_links = set(previous_links)
        self.candidate_urls: list[str] = []
        self.saw_pending = False
        self._handler = self._on_response
        page.on('response', self._handler)

    def _on_response(self, response):
        try:
            if '/api/graphql' not in response.url or response.status != 200:
                return
            body = response.text()
            if 'story_create' not in body and 'ComposerStoryCreate' not in body and 'group_post' not in body:
                return
            for raw_url in re.findall(r'https?:\\/\\/www\.facebook\.com\\/groups\\/[^"\'\s<>]+', body):
                url = post_permalink(raw_url, self.group_url, self.page.url)
                if url and url not in self.previous_links and url not in self.candidate_urls:
                    self.candidate_urls.append(url)
            gpaths = _group_paths(self.group_url, self.page.url)
            if gpaths:
                for pid in re.findall(r'"(?:post_id|legacy_story_hideable_id)"\s*:\s*"(\d{8,})"', body):
                    url = f'https://www.facebook.com{gpaths[0]}/posts/{pid}'
                    if url not in self.previous_links and url not in self.candidate_urls:
                        self.candidate_urls.append(url)
            if re.search(r'"(?:post_status|moderation_state)"\s*:\s*"(?:PENDING|PENDING_APPROVAL|IN_REVIEW)"', body, re.I):
                self.saw_pending = True
        except Exception:
            pass

    def detach(self):
        try:
            self.page.remove_listener('response', self._handler)
        except Exception:
            pass


def composer_images(dialog):
    """Snapshot image identities and readiness in removable photo tiles or multi-photo collages.

    Keep identities on the dialog, so existing avatars or toolbar icons
    cannot become new uploads merely because their source URL changes.
    """
    return dialog.evaluate('''dialog => {
        const state = dialog.__revolandUploadImages ||= {ids: new WeakMap(), next: 0};
        const removePhoto = /^(remove (photo|image|attachment|attachments)|xóa (ảnh|hình|tất cả|file đính kèm)|gỡ (ảnh|hình|tất cả|file đính kèm))(?:\\b|$|\\s)/iu;
        const attachmentBoxes = new Set();
        const images = Array.from(dialog.querySelectorAll('img')).map(img => {
            if (!state.ids.has(img)) state.ids.set(img, ++state.next);
            const src = img.currentSrc || img.src || '';
            const isStaticUiIcon = src.includes('rsrc.php') || src.includes('/images/composer/');
            let tile = img.parentElement;
            let attachment = false;
            if (!isStaticUiIcon) {
                while (tile && tile !== dialog) {
                    if (tile.querySelector('[role="textbox"], [contenteditable="true"]')) break;
                    const controls = tile.querySelectorAll('button[aria-label], [role="button"][aria-label]');
                    if (Array.from(controls).some(button => removePhoto.test(button.getAttribute('aria-label') || ''))) {
                        attachment = true;
                        attachmentBoxes.add(tile);
                        break;
                    }
                    tile = tile.parentElement;
                }
            }
            const visible = img.getClientRects().length > 0 &&
                getComputedStyle(img).visibility !== 'hidden';
            return {id: state.ids.get(img), source: src,
                    attachment, ready: visible && img.complete && img.naturalWidth > 0};
        });
        let overflow = 0;
        for (const box of attachmentBoxes) {
            for (const el of box.querySelectorAll('span, div')) {
                if (el.children.length > 0) continue;
                const m = /^\\+(\\d+)$/.exec((el.textContent || '').trim());
                if (m) overflow = Math.max(overflow, Number(m[1]));
            }
        }
        return {images, overflow};
    }''')


def uploaded_images_ready(dialog, baseline, expected):
    """Require the expected newly attached, decoded images (or Facebook +N collage) and no busy UI."""
    snapshot = composer_images(dialog)
    items = snapshot['images'] if isinstance(snapshot, dict) else snapshot
    overflow = snapshot.get('overflow', 0) if isinstance(snapshot, dict) else 0
    new_images = [image for image in items
                  if image['attachment'] and image['id'] not in baseline]
    count_ok = len(new_images) == expected or (
        len(new_images) >= 4 and overflow >= 1
        and expected in (len(new_images) + overflow, len(new_images) - 1 + overflow)
    )
    return (count_ok and all(image['ready'] for image in new_images)
            and not dialog.locator('[role="progressbar"]:visible, [aria-busy="true"]:visible').count())


def _button_ready(button):
    try:
        return button.is_visible() and button.is_enabled() and button.get_attribute('aria-disabled') != 'true'
    except Exception:
        return False


def _open_composer_dialog(page):
    prompt_re = re.compile(
        r'^(Bạn viết gì đi|Write something|Bạn đang nghĩ gì|What.s on your mind|Tạo bài viết|Create post|Bắt đầu thảo luận|Start a discussion)',
        re.I,
    )
    opener = page.get_by_text(prompt_re)
    if opener.count() and opener.first.is_visible():
        opener.first.click(timeout=12000)
    else:
        btn_opener = page.get_by_role('button', name=prompt_re)
        if btn_opener.count() and btn_opener.first.is_visible():
            btn_opener.first.click(timeout=12000)
        else:
            clicked = page.evaluate('''() => {
                const main = document.querySelector('[role="main"]') || document.body;
                const siblingRe = /^(Bài viết ẩn danh|Anonymous post|Cảm xúc\\/hoạt động|Feeling\\/activity|Thăm dò ý kiến|Poll|Ảnh\\/video|Photo\\/video)$/i;
                const markers = [...main.querySelectorAll('[role="button"], button')].filter(
                    b => !b.closest('[role="article"]') && b.getClientRects().length > 0 &&
                         (siblingRe.test((b.getAttribute('aria-label') || '').trim()) || siblingRe.test((b.innerText || '').trim()))
                );
                for (const m of markers) {
                    let card = m.parentElement;
                    while (card && card !== main) {
                        const buttons = [...card.querySelectorAll('[role="button"], button')].filter(
                            x => x.getClientRects().length > 0 && !siblingRe.test((x.getAttribute('aria-label') || '').trim()) && !siblingRe.test((x.innerText || '').trim())
                        );
                        if (buttons.length) {
                            buttons[0].click();
                            return true;
                        }
                        card = card.parentElement;
                    }
                }
                return false;
            }''')
            if not clicked:
                opener.first.click(timeout=12000)
    dialog = page.get_by_role('dialog').filter(has=page.locator('[contenteditable="true"]')).last
    dialog.wait_for(state='visible', timeout=12000)
    return dialog


class _SharedPostingSession:
    """Lazily opens and reuses one Chromium window with multi-tab support across a batch."""
    def __init__(self, profile_dir: Path, headless: bool):
        self.profile_dir = profile_dir
        self.headless = headless
        self._stack = ExitStack()
        self.context = None
        self._opened = False

    def ensure_context(self):
        if not self._opened:
            self._stack.enter_context(profile_operation(self.profile_dir))
            self._opened = True
            if not self.profile_dir.exists() or not any(self.profile_dir.iterdir()):
                self.context = None
                return None
            p = self._stack.enter_context(sync_playwright())
            self.context = launch_context(p, self.profile_dir, self.headless)
            self._stack.callback(self.context.close)
        return self.context

    def open_tab(self):
        """Open a new tab for a group while keeping active group tabs open in parallel."""
        ctx = self.ensure_context()
        if ctx is None:
            return None, None
        blank_pages = [pg for pg in list(ctx.pages) if pg.url in ('', 'about:blank')]
        page = ctx.new_page()
        for old_blank in blank_pages:
            try:
                old_blank.close()
            except Exception:
                pass
        return ctx, page

    def next_page(self):
        ctx = self.ensure_context()
        if ctx is None:
            return None, None
        existing = list(ctx.pages)
        page = ctx.new_page()
        for old_page in existing:
            try:
                old_page.close()
            except Exception:
                pass
        return ctx, page

    def close(self):
        self._stack.close()


class FacebookPosterEngine:
    def __init__(self, profile_dir=None):
        self.profile_dir = Path(profile_dir or PROFILE_DIR)
        self.config = load_config()
        self.upload_timeout = 60
        self.confirmation_timeout = 40

    @contextmanager
    def posting_session(self, headless=None):
        """Yield a reusable single-window browser session for multi-group posting & auto-verification."""
        use_headless = headless if headless is not None else self.config.get('headless_posting', False)
        session = _SharedPostingSession(self.profile_dir, use_headless)
        try:
            yield session
        finally:
            session.close()

    def _compose_and_click_submit(self, page, context, group, post_content, image_paths, before_submit, result, mark_submitted):
        """Navigate to group, fill approved content & photos, and click Đăng. Returns (err_result, dialog, previous, prior_notices, monitor)."""
        page.goto(group.group_url, timeout=45000, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        if not authenticated(page, context):
            return result(Status.ACTION_REQUIRED, 'Cần đăng nhập hoặc hoàn tất xác minh Facebook.'), None, set(), set(), None
        previous = collect_feed_permalinks(page, group.group_url)
        previous.update(_relay_permalinks_on_page(page, group.group_url))
        dialog = _open_composer_dialog(page)
        page.wait_for_timeout(600)

        clear_draft_btn = dialog.get_by_role(
            'button',
            name=re.compile(r'^(Gỡ file đính kèm trong bài viết|Remove attachments from your post|Gỡ file đính kèm|Remove attachments)$', re.I),
        )
        if clear_draft_btn.count() and clear_draft_btn.first.is_visible():
            clear_draft_btn.first.click(timeout=5000)
            page.wait_for_timeout(500)

        existing_snapshot = composer_images(dialog)
        existing_images = existing_snapshot['images'] if isinstance(existing_snapshot, dict) else existing_snapshot
        if any(image['attachment'] for image in existing_images):
            return result(Status.FAILED, 'Cửa sổ soạn đang có ảnh từ bản nháp cũ. Hãy xóa bản nháp trước khi thử lại.'), None, previous, set(), None
        baseline = {image['id'] for image in existing_images}

        editor = dialog.locator('[contenteditable="true"][role="textbox"]').first
        editor.click(timeout=8000)
        editor.fill(post_content)
        if normalize_text(editor.inner_text()) != normalize_text(post_content):
            return result(Status.FAILED, 'Nội dung trong ô soạn không khớp bản xem trước. Chưa gửi bài.'), None, previous, set(), None

        if image_paths:
            photo_btn = dialog.get_by_role(
                'button',
                name=re.compile(r'^(Ảnh\/video|Photo\/video|Thêm ảnh\/video|Add photos\/videos)$', re.I),
            )
            if photo_btn.count() and photo_btn.first.is_visible():
                with page.expect_file_chooser(timeout=15000) as chooser:
                    photo_btn.first.click(timeout=10000)
                chooser.value.set_files(image_paths)
            else:
                file_input = dialog.locator('input[type="file"][accept*="image"]').first
                if not file_input.count():
                    dialog.get_by_text(re.compile(r'^(Ảnh\/video|Photo\/video)$', re.I)).first.click(timeout=10000)
                file_input.set_input_files(image_paths, timeout=15000)

            timeout_sec = (max(float(self.upload_timeout), min(300.0, len(image_paths) * 8.0))
                           if self.upload_timeout >= 60 else float(self.upload_timeout))
            deadline = time.monotonic() + timeout_sec
            while time.monotonic() < deadline:
                if uploaded_images_ready(dialog, baseline, len(image_paths)):
                    break
                page.wait_for_timeout(500)
            else:
                return result(Status.FAILED, 'Chưa xác nhận tải đủ ảnh. Chưa gửi bài.'), None, previous, set(), None

            if normalize_text(editor.inner_text()) != normalize_text(post_content):
                editor.fill(post_content)
                if normalize_text(editor.inner_text()) != normalize_text(post_content):
                    return result(Status.FAILED, 'Nội dung trong ô soạn không khớp sau khi đính kèm ảnh. Chưa gửi bài.'), None, previous, set(), None

        next_btn = dialog.get_by_role('button', name=re.compile(r'^(Tiếp|Next)$'))
        if next_btn.count() and not dialog.get_by_role('button', name=re.compile(r'^(Đăng|Post)$')).count():
            next_btn.last.click(timeout=8000)
            dialog = page.get_by_role('dialog').last
            dialog.get_by_role('button', name=re.compile(r'^(Đăng|Post)$')).last.wait_for(state='visible', timeout=10000)

        submit = dialog.get_by_role('button', name=re.compile(r'^(Đăng|Post)$')).last
        btn_deadline = time.monotonic() + min(8.0, float(self.upload_timeout))
        while time.monotonic() < btn_deadline and not _button_ready(submit):
            page.wait_for_timeout(300)
        if not _button_ready(submit):
            return result(Status.FAILED, 'Facebook chưa cho phép gửi bài. Kiểm tra nội dung và ảnh.'), None, previous, set(), None

        prior_notices = {n.inner_text() for n in page.locator('[role="alert"], [role="status"]').all() if n.is_visible()}
        monitor = _GraphQLSubmitMonitor(page, group.group_url, previous)
        if before_submit:
            before_submit()
        mark_submitted()
        submit.click(timeout=12000)
        return None, dialog, previous, prior_notices, monitor

    def _check_tab_once(self, page, context, dialog, group, post_content, previous, prior_notices, monitor, result):
        """Non-destructive check on an open group tab right after submit. Returns GroupTaskResult or None."""
        if not authenticated(page, context):
            return result(Status.UNKNOWN, 'Facebook yêu cầu xác minh sau khi gửi; kiểm tra nhóm trước khi thử lại.')
        url = confirmed_post(page, post_content, group.group_url, previous)
        if url:
            return result(Status.POSTED, url=url, evidence='fresh_permalink_and_full_content')
        dialog_open = False
        if dialog is not None:
            try:
                dialog_open = dialog.is_visible()
            except Exception:
                dialog_open = False
        if not dialog_open:
            notices = page.locator('[role="alert"], [role="status"]')
            for notice in notices.all():
                try:
                    if not notice.is_visible():
                        continue
                    txt = notice.inner_text()
                    if txt not in prior_notices:
                        for link in notice.locator('a[href]').all():
                            toast_url = post_permalink(link.get_attribute('href') or '', group.group_url, page.url)
                            if toast_url and toast_url not in previous:
                                return result(Status.POSTED, url=toast_url, evidence='published_toast_permalink')
                        if _PENDING_NOTICE_RE.search(txt):
                            return result(Status.PENDING_APPROVAL, 'Bài đã gửi và đang chờ duyệt.', evidence='submission_pending_notice')
                except Exception:
                    continue
            if monitor is not None and monitor.saw_pending:
                return result(Status.PENDING_APPROVAL, 'Bài đã gửi và đang chờ duyệt.', evidence='graphql_pending_moderation')
        return None

    def _active_verify_on_page(self, page, context, group, post_content, previous_links=frozenset(), monitor=None, result=None):
        """Actively navigate to chronological group feed, my_posted_content, and my_pending_content to auto-verify."""
        base = group.group_url.rstrip('/')
        sep = '&' if '?' in base else '?'
        check_urls = [
            (f'{base}{sep}sorting_setting=CHRONOLOGICAL', 'auto_verified_chronological_feed'),
            (f'{base}/my_posted_content', 'auto_verified_my_posted_content'),
        ]
        if monitor is not None:
            for cand_url in list(monitor.candidate_urls)[:2]:
                check_urls.insert(0, (cand_url, 'auto_verified_graphql_permalink'))

        for target_url, evidence_tag in check_urls:
            try:
                page.goto(target_url, timeout=35000, wait_until='domcontentloaded')
                page.wait_for_timeout(2800)
                if not authenticated(page, context):
                    return result(Status.UNKNOWN, 'Facebook yêu cầu đăng nhập lại trong lúc tự kiểm tra kết quả.')
                if target_url in (monitor.candidate_urls if monitor else []):
                    main_loc = page.locator('[role="main"]')
                    if main_loc.count():
                        more = main_loc.get_by_role('button', name=re.compile(r'^(Xem thêm|See more)$', re.I))
                        if more.count() and more.first.is_visible():
                            try:
                                more.first.click(timeout=2000)
                                page.wait_for_timeout(300)
                            except Exception:
                                pass
                        if text_contains_approved_content(main_loc.first.inner_text(), post_content):
                            return result(Status.POSTED, url=target_url, evidence=evidence_tag)
                found_url = confirmed_post(page, post_content, group.group_url, previous_links)
                if found_url:
                    return result(Status.POSTED, url=found_url, evidence=evidence_tag)
                main_text = page.locator('[role="main"]').first.inner_text() if page.locator('[role="main"]').count() else ''
                if re.search(r'(\d+\s*bài viết đang chờ phê duyệt|\d+\s*posts?\s+pending\s+approval)', main_text, re.I):
                    # Confirm inside my_pending_content below
                    break
            except Exception:
                continue

        # Check member's pending queue (/my_pending_content)
        try:
            page.goto(f'{base}/my_pending_content', timeout=30000, wait_until='domcontentloaded')
            page.wait_for_timeout(2500)
            if authenticated(page, context) and page.locator('[role="main"]').count():
                main = page.locator('[role="main"]').first
                for more in main.get_by_role('button', name=re.compile(r'^(Xem thêm|See more)$', re.I)).all()[:3]:
                    try:
                        if more.is_visible():
                            more.click(timeout=1500)
                            page.wait_for_timeout(250)
                    except Exception:
                        pass
                if text_contains_approved_content(main.inner_text(), post_content):
                    return result(Status.PENDING_APPROVAL, 'Đã tự xác nhận bài nằm trong mục chờ admin nhóm duyệt.', evidence='auto_verified_my_pending_content')
        except Exception:
            pass
        return None

    def _submit_on_page(self, page, context, group, post_content, image_paths, before_submit, result, mark_submitted):
        err, dialog, previous, prior_notices, monitor = self._compose_and_click_submit(
            page, context, group, post_content, image_paths, before_submit, result, mark_submitted
        )
        if err is not None:
            return err
        try:
            # Poll current page first (fast path for immediate feed render & offline tests)
            initial_window = min(float(self.confirmation_timeout), 10.0)
            deadline = time.monotonic() + initial_window
            while time.monotonic() < deadline:
                checked = self._check_tab_once(page, context, dialog, group, post_content, previous, prior_notices, monitor, result)
                if checked is not None:
                    return checked
                page.wait_for_timeout(900)

            # If real confirmation budget allows (>= 10s), actively verify via chronological feed & my_posted_content
            if self.confirmation_timeout >= 10:
                verified = self._active_verify_on_page(page, context, group, post_content, previous, monitor, result)
                if verified is not None:
                    return verified

                remaining = (time.monotonic() + max(0.0, float(self.confirmation_timeout) - initial_window - 8.0))
                while time.monotonic() < remaining:
                    checked = self._check_tab_once(page, context, None, group, post_content, previous, prior_notices, monitor, result)
                    if checked is not None:
                        return checked
                    page.wait_for_timeout(1000)

            return result(Status.UNKNOWN, 'Đã bấm gửi nhưng chưa thấy bài trên nhóm sau khi tự kiểm tra. Tool không tự đăng lại.')
        finally:
            if monitor is not None:
                monitor.detach()

    def post_to_single_group(self, task_id, group, post_content, image_paths,
                             headless=None, before_submit=None, shared_session=None):
        submitted = False
        def mark_submitted():
            nonlocal submitted
            submitted = True

        def result(status, message=None, url=None, evidence=None):
            return GroupTaskResult(task_id=task_id, group_id=group.id, group_name=group.name,
                group_url=group.group_url, status=status, error_message=message, post_url=url,
                evidence=evidence, submission_started=submitted,
                posted_at=utc_now_iso() if status in (Status.POSTED, Status.PENDING_APPROVAL) else None)

        if not post_content.strip():
            return result(Status.FAILED, 'Nội dung bài viết trống.')
        if any(not Path(path).is_file() for path in image_paths):
            return result(Status.FAILED, 'Thiếu file ảnh đã xem trước. Hãy tạo lại chiến dịch.')
        try:
            if shared_session is not None:
                context, page = shared_session.next_page()
                if context is None or page is None:
                    return result(Status.ACTION_REQUIRED, 'Chưa có phiên Facebook. Hãy đăng nhập trước.')
                return self._submit_on_page(page, context, group, post_content, image_paths, before_submit, result, mark_submitted)

            with profile_operation(self.profile_dir):
                if not self.profile_dir.exists() or not any(self.profile_dir.iterdir()):
                    return result(Status.ACTION_REQUIRED, 'Chưa có phiên Facebook. Hãy đăng nhập trước.')
                with sync_playwright() as p:
                    context = launch_context(p, self.profile_dir,
                        headless if headless is not None else self.config.get('headless_posting', False))
                    try:
                        page = context.new_page()
                        return self._submit_on_page(page, context, group, post_content, image_paths, before_submit, result, mark_submitted)
                    finally:
                        context.close()
        except ResourceBusyError as exc:
            return result(Status.ACTION_REQUIRED, str(exc))
        except Exception as exc:
            logging.getLogger(__name__).warning('Facebook interaction failed (%s: %s), submission_started=%s', type(exc).__name__, exc, submitted)
            return result(Status.UNKNOWN if submitted else Status.FAILED,
                'Mất xác nhận sau khi gửi. Kiểm tra nhóm trước khi thử lại.' if submitted else
                'Không thao tác được giao diện Facebook. Chưa gửi bài; kiểm tra mạng, quyền đăng và giao diện nhóm.')

    def post_batch_parallel(self, items, post_content, image_paths, min_delay=5.0, max_delay=10.0,
                            on_task_start=None, on_before_submit=None, on_task_done=None, headless=None):
        """Post up to five groups concurrently using the same authenticated account.

        Each worker owns its browser and Playwright runtime. The account profile
        stays locked until every worker finishes; disk profiles are never shared
        across browsers. Callbacks serialize updates to the campaign snapshot.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from threading import Event, Lock
        from services.facebook_browser import isolated_posting_context

        if not items:
            return {}
        if len(items) > 5:
            raise ValueError('Mỗi đợt chỉ đăng đồng thời tối đa 5 nhóm.')
        callbacks = Lock()
        halt = Event()
        results = {}
        use_headless = headless if headless is not None else self.config.get('headless_posting', False)

        class BatchHalted(Exception):
            pass

        def callback(fn, *args):
            if fn:
                with callbacks:
                    fn(*args)

        def worker(task_id, group, storage_state):
            submitted = False

            def result(status, message=None, url=None, evidence=None):
                return GroupTaskResult(
                    task_id=task_id, group_id=group.id, group_name=group.name,
                    group_url=group.group_url, status=status, error_message=message,
                    post_url=url, evidence=evidence, submission_started=submitted,
                    posted_at=utc_now_iso() if status in (Status.POSTED, Status.PENDING_APPROVAL) else None,
                )

            def before_submit():
                if halt.is_set():
                    raise BatchHalted()
                callback(on_before_submit, task_id)

            def mark_submitted():
                nonlocal submitted
                submitted = True

            callback(on_task_start, task_id)
            try:
                if not post_content.strip() or any(not Path(path).is_file() for path in image_paths):
                    res = result(Status.FAILED, 'Nội dung trống hoặc thiếu file ảnh đã xem trước. Chưa gửi bài.')
                else:
                    with isolated_posting_context(storage_state, use_headless) as context:
                        page = context.new_page()
                        res = self._submit_on_page(page, context, group, post_content, image_paths,
                                                   before_submit, result, mark_submitted)
            except BatchHalted:
                res = result(Status.ACTION_REQUIRED, 'Tạm dừng nhóm chưa gửi vì nhóm khác cần kiểm tra Facebook.')
            except Exception as exc:
                logging.getLogger(__name__).warning('Concurrent group failed (%s)', type(exc).__name__)
                res = result(Status.UNKNOWN if submitted else Status.FAILED,
                             'Đã bắt đầu gửi nhưng mất xác nhận. Kiểm tra nhóm trước khi thử lại.' if submitted else
                             'Không thao tác được Facebook. Chưa gửi bài; kiểm tra kết nối và phiên đăng nhập.')
            if res.status == Status.ACTION_REQUIRED:
                halt.set()
            return res

        with self.posting_session(headless=True) as session:
            context = session.ensure_context()
            storage_state = context.storage_state() if context is not None else None
            if storage_state is None or not any(c.get('name') == 'c_user' and c.get('value')
                                                for c in storage_state.get('cookies', [])):
                for task_id, group in items:
                    res = GroupTaskResult(task_id=task_id, group_id=group.id, group_name=group.name,
                                          group_url=group.group_url, status=Status.ACTION_REQUIRED,
                                          error_message='Chưa có phiên Facebook. Hãy đăng nhập trước.')
                    results[task_id] = res
                    callback(on_task_done, task_id, res)
                return results
            with ThreadPoolExecutor(max_workers=len(items), thread_name_prefix='facebook-group') as pool:
                futures = {pool.submit(worker, tid, group, storage_state): tid for tid, group in items}
                for future in as_completed(futures):
                    tid = futures[future]
                    res = future.result()
                    results[tid] = res
                    callback(on_task_done, tid, res)
        return results

    def check_saved_post(self, post_url, group, post_content, headless=True, shared_session=None):
        """Read a saved permalink without submitting or changing posting history."""
        target = post_permalink(post_url, group.group_url)
        if not target:
            return {'status': 'unknown', 'message': 'Link bài đã lưu không đúng nhóm; chưa kiểm tra được.'}

        def inspect(session):
            context, page = session.next_page()
            if context is None or page is None:
                return {'status': 'action_required', 'message': 'Cần đăng nhập Facebook để kiểm tra link.'}
            page.goto(target, timeout=45000, wait_until='domcontentloaded')
            page.wait_for_timeout(2000)
            has_user = any(c.get('name') == 'c_user' and c.get('value')
                           for c in context.cookies('https://www.facebook.com/'))
            path = urlsplit(page.url).path.lower()
            if (not has_user or any(word in path for word in ('login', 'checkpoint', 'recover', 'two_step', 'auth_platform', 'consent'))
                    or page.locator('input[name="email"], input[name="pass"]').count()):
                return {'status': 'action_required', 'message': 'Facebook cần đăng nhập/xác minh; chưa kết luận tình trạng bài.'}
            unavailable = page.get_by_text(re.compile(
                r"^(This content isn't available(?: right now)?|This page isn't available(?: right now)?|"
                r"Nội dung này hiện không hiển thị|Bạn hiện không xem được nội dung này|Trang này hiện không hiển thị)", re.I))
            if any(item.is_visible() for item in unavailable.all()):
                return {'status': 'unavailable', 'message': 'Link không còn hiển thị với tài khoản này. Bài có thể đã bị xóa, ẩn hoặc đổi quyền truy cập.'}
            if not authenticated(page, context):
                return {'status': 'unknown', 'message': 'Chưa nhận diện đủ giao diện Facebook để kết luận tình trạng link.'}
            target_id = urlsplit(target).path.rstrip('/').split('/')[-1]
            other_posts = {url for url in collect_feed_permalinks(page, group.group_url)
                           if urlsplit(url).path.rstrip('/').split('/')[-1] != target_id}
            found = confirmed_post(page, post_content, group.group_url, other_posts)
            if found and urlsplit(found).path.rstrip('/').split('/')[-1] == target_id:
                return {'status': 'available', 'message': 'Bài còn truy cập được và khớp nội dung đã đăng.'}
            return {'status': 'unknown', 'message': 'Đã mở link nhưng chưa xác nhận được bài mục tiêu; giữ nguyên link và lịch sử.'}

        try:
            if shared_session is not None:
                return inspect(shared_session)
            with self.posting_session(headless=headless) as session:
                return inspect(session)
        except ResourceBusyError as exc:
            return {'status': 'action_required', 'message': str(exc)}
        except Exception as exc:
            return {'status': 'unknown', 'message': f'Chưa kiểm tra được link ({type(exc).__name__}). Không kết luận bài đã bị xóa.'}

    def auto_verify_group_post(self, task_id, group, post_content, known_urls=frozenset(),
                               headless=True, shared_session=None):
        """Automatically inspect Facebook group feed & pending queue for an unconfirmed/pending post without reposting."""
        def result(status, message=None, url=None, evidence=None):
            return GroupTaskResult(
                task_id=task_id, group_id=group.id, group_name=group.name,
                group_url=group.group_url, status=status, error_message=message,
                post_url=url, evidence=evidence, submission_started=True,
                posted_at=utc_now_iso() if status in (Status.POSTED, Status.PENDING_APPROVAL) else None,
            )

        try:
            if shared_session is not None:
                context, page = shared_session.next_page()
                if context is None or page is None:
                    return result(Status.ACTION_REQUIRED, 'Chưa có phiên Facebook. Hãy đăng nhập trước.')
                verified = self._active_verify_on_page(page, context, group, post_content, set(known_urls), None, result)
                return verified or result(
                    Status.UNKNOWN,
                    'Đã tự kiểm tra bảng feed mới nhất và mục chờ duyệt nhưng chưa thấy bài viết này.',
                )

            with self.posting_session(headless=headless) as session:
                context, page = session.next_page()
                if context is None or page is None:
                    return result(Status.ACTION_REQUIRED, 'Chưa có phiên Facebook. Hãy đăng nhập trước.')
                verified = self._active_verify_on_page(page, context, group, post_content, set(known_urls), None, result)
                return verified or result(
                    Status.UNKNOWN,
                    'Đã tự kiểm tra bảng feed mới nhất và mục chờ duyệt nhưng chưa thấy bài viết này.',
                )
        except ResourceBusyError as exc:
            return result(Status.ACTION_REQUIRED, str(exc))
        except Exception as exc:
            logging.getLogger(__name__).warning('Auto verify failed (%s: %s)', type(exc).__name__, exc)
            return result(Status.UNKNOWN, 'Không thể tự kiểm tra nhóm lúc này. Vui lòng thử lại sau vài giây.')
