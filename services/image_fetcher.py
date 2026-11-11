"""Tải ảnh cho bài đăng: hỗ trợ link ảnh sau Cloudflare, ảnh base64 và ảnh trên máy.

Thứ tự thử cho mỗi link HTTP(S):
1. ``requests`` với header giống trình duyệt Chrome thật (User-Agent, Accept ảnh, Sec-Fetch-*, Referer).
   Xử lý ngay các trường hợp chặn User-Agent lạ hoặc chống hotlink (thiếu Referer).
2. Nếu vẫn bị chặn (Cloudflare challenge / Bot Fight Mode / WAF trả 403, 429, 503 hoặc trả HTML thay vì ảnh):
   - Thử ngầm bằng Chromium thật (TLS/HTTP2 thật, ẩn dấu hiệu tự động) trong vài giây để tự vượt các trang không cần bấm tay.
   - Nếu trang yêu cầu bấm xác minh Turnstile ("Verify you are human"), mở cửa sổ Chromium với hồ sơ riêng để
     người dùng bấm xác minh một lần; các ảnh cùng tên miền tiếp theo tải trực tiếp qua phiên đã xác minh.
"""
from __future__ import annotations

import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import inspect
import io
import os
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import unquote, urljoin, urlsplit

from PIL import Image
import requests

from config.settings import ROOT_DIR

Image.MAX_IMAGE_PIXELS = None

BROWSER_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
IMAGE_ACCEPT = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
DOWNLOAD_WORKERS = 8
_BROWSER_LOCK = threading.Lock()


class BlockedDownloadError(ValueError):
    """Nguồn chặn tải tự động (Cloudflare, chống hotlink, 403/429/503) — có thể thử bằng trình duyệt."""


def default_browser_profile_dir() -> Path:
    runtime = Path(os.getenv('REVOLAND_DATA_DIR', str(ROOT_DIR))).resolve()
    return runtime / 'browser_data' / 'image_downloader'


def browser_fallback_enabled() -> bool:
    return os.getenv('REVOLAND_IMAGE_BROWSER', '1').strip().lower() not in ('0', 'false', 'no', 'off')


def browser_headers(url: str, referer: str | None = None, accept: str = IMAGE_ACCEPT) -> dict:
    parts = urlsplit(url)
    origin = f'{parts.scheme}://{parts.netloc}/'
    ref = referer or origin
    same_site = urlsplit(ref).hostname == parts.hostname
    return {
        'User-Agent': BROWSER_USER_AGENT,
        'Accept': accept,
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': ref,
        'Sec-Fetch-Dest': 'image' if accept == IMAGE_ACCEPT else 'document',
        'Sec-Fetch-Mode': 'no-cors' if accept == IMAGE_ACCEPT else 'navigate',
        'Sec-Fetch-Site': 'same-origin' if same_site else 'cross-site',
        'Sec-Ch-Ua': '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
    }


def is_cloudflare_block(status: int, headers, body_prefix: bytes = b'') -> bool:
    if str(headers.get('cf-mitigated', '')).lower() == 'challenge':
        return True
    lower_headers = {str(k).lower(): str(v).lower() for k, v in headers.items()} if hasattr(headers, 'items') else {}
    server = lower_headers.get('server', '')
    has_cf = 'cloudflare' in server or 'cf-ray' in lower_headers
    text = body_prefix[:4096].decode('utf-8', errors='replace').lower()
    markers = ('just a moment', 'cf-chl', 'challenge-platform', 'attention required', 'cf-browser-verification',
               '__cf_chl', 'cloudflare ray id', 'turnstile')
    return (has_cf and status in (403, 429, 503)) or any(m in text for m in markers)


def looks_like_html(raw: bytes) -> bool:
    head = raw[:512].lstrip().lower()
    return head.startswith((b'<!doctype html', b'<html', b'<head', b'<?xml version')) and b'<svg' not in head


def is_valid_image_bytes(raw: bytes | None) -> bool:
    if not raw or looks_like_html(raw):
        return False
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- ảnh không phải HTTP
def decode_data_uri(value: str) -> bytes:
    header, _, payload = value.partition(',')
    if not payload:
        raise ValueError('Ảnh base64 (data:) không có dữ liệu.')
    try:
        if ';base64' in header.lower():
            return base64.b64decode(payload.strip(), validate=False)
        return unquote(payload).encode('latin-1')
    except (binascii.Error, ValueError) as exc:
        raise ValueError('Ảnh base64 (data:) không đọc được.') from exc


def local_image_path(value: str, base_dir: Path | None = None) -> Path | None:
    """Trả về đường dẫn file trên máy nếu ``value`` là file:// hoặc đường dẫn ổ đĩa/file có thật."""
    text = value.strip()
    if text.lower().startswith('file:'):
        parts = urlsplit(text)
        raw = unquote(parts.path)
        if parts.netloc and parts.netloc.lower() != 'localhost':
            raw = f'//{parts.netloc}{raw}'
        if len(raw) > 2 and raw[0] == '/' and raw[2] == ':':  # /C:/...
            raw = raw[1:]
        return Path(raw)
    if '://' in text or text.startswith('//'):
        return None
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    if path.is_file() or re.match(r'^(?:[a-zA-Z]:[\\/]|\\\\)', text):
        return path
    return None


def normalize_image_ref(value: str, base_url: str = '') -> str:
    text = value.strip()
    if text.startswith('//'):
        return (urlsplit(base_url).scheme or 'https') + ':' + text
    if base_url and '://' not in text and not text.lower().startswith(('data:', 'file:')) and local_image_path(text) is None:
        return urljoin(base_url, text)
    return text


def _call_fetch_http(fetch_http, url: str, referer: str | None):
    try:
        params = inspect.signature(fetch_http).parameters
        accepts_referer = 'referer' in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except (TypeError, ValueError):
        accepts_referer = True
    if accepts_referer:
        return fetch_http(url, None, referer=referer)
    return fetch_http(url, None)


# ---------------------------------------------------------------- trình duyệt dự phòng
class BrowserImageFetcher:
    """Tải ảnh bằng Chromium thật; tái sử dụng phiên đã qua Cloudflare cho các ảnh cùng tên miền."""

    def __init__(self, profile_dir: Path | None = None, headless_wait: float = 6.0, visible_wait: float = 150.0):
        self.profile_dir = Path(profile_dir) if profile_dir else default_browser_profile_dir()
        self.headless_wait = headless_wait
        self.visible_wait = visible_wait
        self._pw = None
        self._context = None
        self._headless = None
        self._origin_pages: dict[str, object] = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._origin_pages.clear()
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._context = self._pw = self._headless = None

    def _open(self, headless: bool):
        if self._context is not None and self._headless == headless:
            return self._context
        self.close()
        from playwright.sync_api import sync_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=headless,
            user_agent=BROWSER_USER_AGENT,
            **({'executable_path': self._pw.chromium.executable_path} if getattr(sys, 'frozen', False) else {}),
            viewport={'width': 1100, 'height': 800},
            locale='vi-VN',
            args=['--disable-blink-features=AutomationControlled', '--disable-save-password-bubble'],
        )
        self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        self._context.route(
            '**/*',
            lambda route: route.continue_()
            if route.request.url.lower().startswith(('http://', 'https://', 'data:', 'blob:', 'about:'))
            else route.abort(),
        )
        self._headless = headless
        return self._context

    @staticmethod
    def _fetch_in_page(page, url: str) -> bytes | None:
        """Tải ảnh ngay trong ngữ cảnh trang cùng origin (dùng TLS + cookie cf_clearance của Chromium)."""
        try:
            b64 = page.evaluate(
                """async (targetUrl) => {
                    const resp = await fetch(targetUrl, {
                        credentials: 'include',
                        headers: {'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'}
                    });
                    if (!resp.ok) return null;
                    const ctype = (resp.headers.get('content-type') || '').toLowerCase();
                    if (ctype.includes('text/html')) return null;
                    const bytes = new Uint8Array(await resp.arrayBuffer());
                    let binary = '';
                    for (let i = 0; i < bytes.length; i += 0x8000) {
                        binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                    }
                    return btoa(binary);
                }""",
                url,
            )
            if not b64:
                return None
            raw = base64.b64decode(b64)
            return raw if is_valid_image_bytes(raw) else None
        except Exception:
            return None

    def _try_page(self, context, url: str, referer: str | None, wait_seconds: float) -> bytes | None:
        parts = urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        cached_page = self._origin_pages.get(origin)
        if cached_page is not None:
            try:
                if not cached_page.is_closed():
                    fast = self._fetch_in_page(cached_page, url)
                    if fast:
                        return fast
            except Exception:
                pass
            self._origin_pages.pop(origin, None)

        page = context.new_page()
        captured: list[bytes] = []

        def on_response(response):
            try:
                if (
                    response.status == 200
                    and response.frame == page.main_frame
                    and response.request.is_navigation_request()
                    and 'challenges.cloudflare.com' not in response.url.lower()
                ):
                    body = response.body()
                    if is_valid_image_bytes(body):
                        captured.append(body)
            except Exception:
                pass

        page.on('response', on_response)
        keep_page = False
        try:
            try:
                page.goto(url, referer=referer, wait_until='commit', timeout=30000)
            except Exception:
                pass
            deadline = time.monotonic() + wait_seconds
            last_probe = time.monotonic()
            while time.monotonic() < deadline:
                if captured:
                    keep_page = True
                    self._origin_pages[origin] = page
                    return captured[-1]
                page.wait_for_timeout(600)
                if captured:
                    keep_page = True
                    self._origin_pages[origin] = page
                    return captured[-1]
                if time.monotonic() - last_probe >= 3.5:
                    title = ''
                    current_origin = ''
                    try:
                        title = page.title().lower()
                        cur = urlsplit(page.url)
                        current_origin = f'{cur.scheme}://{cur.netloc}'
                    except Exception:
                        pass
                    in_challenge = any(m in title for m in ('just a moment', 'chờ một chút', 'attention required'))
                    if not in_challenge and current_origin == origin:
                        fetched = self._fetch_in_page(page, url)
                        if fetched:
                            keep_page = True
                            self._origin_pages[origin] = page
                            return fetched
                        try:
                            page.goto(url, referer=referer, wait_until='commit', timeout=25000)
                        except Exception:
                            pass
                    last_probe = time.monotonic()
            return None
        finally:
            if not keep_page:
                try:
                    page.close()
                except Exception:
                    pass

    def fetch(self, url: str, referer: str | None = None) -> bytes:
        with _BROWSER_LOCK:
            if self._headless is not False and self.headless_wait > 0:
                body = self._try_page(self._open(True), url, referer, self.headless_wait)
                if body:
                    return body
            body = self._try_page(self._open(False), url, referer, self.visible_wait)
            if body:
                return body
        raise BlockedDownloadError(
            'Nguồn ảnh yêu cầu xác minh Cloudflare và chưa xác minh xong trong cửa sổ trình duyệt. '
            'Hãy nạp lại và bấm xác minh khi cửa sổ hiện lên, hoặc dùng link ảnh khác.'
        )


def download_many(refs: list[tuple[str, str | None]], fetch_http, *, base_dir: Path | None = None,
                  use_browser: bool | None = None) -> list[tuple[bytes | None, str | None]]:
    """Tải nhiều ảnh song song. ``refs`` là danh sách (ảnh, referer). Trả về (dữ liệu, lỗi) theo thứ tự."""
    results: list[tuple[bytes | None, str | None]] = [(None, None)] * len(refs)
    blocked: list[int] = []

    def one(index: int):
        ref, referer = refs[index]
        try:
            if ref.lower().startswith('data:'):
                return index, decode_data_uri(ref), None, False
            path = local_image_path(ref, base_dir)
            if path is not None or ref.lower().startswith('file:'):
                if path is None or not path.is_file():
                    return index, None, 'Không tìm thấy file ảnh trên máy.', False
                return index, path.read_bytes(), None, False
            if not ref.lower().startswith(('http://', 'https://')):
                return index, None, 'Đường dẫn ảnh không hợp lệ (cần link http(s), ảnh base64 hoặc file trên máy).', False
            raw = _call_fetch_http(fetch_http, ref, referer)[0]
            if looks_like_html(raw):
                raise BlockedDownloadError('Link trả về trang web thay vì ảnh (có thể là trang xác minh Cloudflare).')
            return index, raw, None, False
        except BlockedDownloadError as exc:
            return index, None, str(exc), True
        except Exception as exc:  # noqa: BLE001 - báo lỗi từng ảnh, không làm hỏng cả đợt nạp
            return index, None, str(exc) or 'Không tải được ảnh.', False

    if refs:
        with ThreadPoolExecutor(max_workers=min(DOWNLOAD_WORKERS, len(refs)), thread_name_prefix='image-dl') as pool:
            for index, raw, error, is_blocked in pool.map(one, range(len(refs))):
                results[index] = (raw, error)
                if is_blocked:
                    blocked.append(index)

    if blocked and (browser_fallback_enabled() if use_browser is None else use_browser):
        fetcher = BrowserImageFetcher()
        try:
            for index in blocked:
                ref, referer = refs[index]
                try:
                    results[index] = (fetcher.fetch(ref, referer), None)
                except Exception as exc:  # noqa: BLE001
                    results[index] = (None, str(exc) or results[index][1])
        finally:
            fetcher.close()
    return results
