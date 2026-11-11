"""Public JSON/JSON-LD property sources and direct user-authored listings, with immutable local image snapshots."""
import base64
import binascii
import hashlib
from html import unescape
from html.parser import HTMLParser
import io
import ipaddress
import json
import logging
import math
from pathlib import Path
import re
import socket
import sqlite3
import threading
from contextlib import closing
from decimal import Decimal
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
import uuid

from PIL import Image, ImageOps
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import Field

from config.settings import ROOT_DIR, RUNTIME_DIR
from models.schema import PropertyListing, utc_now_iso
from services.input_errors import InputError
from services.image_fetcher import (BlockedDownloadError, browser_headers, download_many,
                                    is_cloudflare_block, local_image_path, normalize_image_ref)

# Ảnh rất lớn vẫn nhận (không chặn theo megapixel), nhưng được thu nhỏ khi lưu để đăng nhanh.
Image.MAX_IMAGE_PIXELS = None
MAX_SAVED_IMAGE_SIDE = 4096
IMAGE_DOWNLOAD_BATCH_SIZE = 32


def save_image_snapshot(raw: bytes, path: Path) -> str:
    """Chuẩn hóa ảnh (JPG/PNG/WebP/AVIF/GIF...) về JPEG và trả về SHA-256 của file đã lưu."""
    with Image.open(io.BytesIO(raw)) as image:
        image.seek(0)
        image = ImageOps.exif_transpose(image)
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGBA')
            background = Image.new('RGB', image.size, '#ffffff')
            background.paste(image, mask=image.getchannel('A'))
            image = background
        else:
            image = image.convert('RGB')
        image.thumbnail((MAX_SAVED_IMAGE_SIDE, MAX_SAVED_IMAGE_SIDE), Image.LANCZOS)
        image.save(path, 'JPEG', quality=92)
    return hashlib.sha256(path.read_bytes()).hexdigest()

QUINLAND_DEFAULT_INDICES = (0, 4, 5, 10, 12, 13, 20, 34)
_QUINLAND_TYPE_LABELS = {
    'Apartment': 'Căn hộ chung cư',
    'MiniServiceApartment': 'Căn hộ dịch vụ',
    'SocialHousing': 'Nhà ở / Căn hộ',
    'House': 'Nhà riêng',
    'Townhouse': 'Nhà phố mặt tiền',
    'LandPlot': 'Đất nền',
    'ProjectLand': 'Đất dự án',
    'Office': 'Văn phòng',
    'Other': 'Bất động sản',
}
_PHONE_RE = re.compile(r'(?<!\d)(?:\+?84|0)(?:[\s.\-]*\d){8,9}(?!\d)')
_CONTENT_KEYS = ('content', 'post_text', 'description', 'text', 'message', 'body', 'caption')
_IMAGE_KEYS = ('images', 'media_urls', 'image_urls', 'photos', 'pictures', 'image')


def revoland_property_id(url):
    parts = urlsplit(url)
    candidate = parts.path.rstrip('/').rsplit('/', 1)[-1]
    if parts.hostname in ('revoland.vn', 'www.revoland.vn') and re.fullmatch(r'[0-9a-fA-F]{24}', candidate):
        return candidate.lower()
    return None


def revoland_page_property(html, expected_id):
    """Read Next.js JSON records without executing scripts from the source."""
    decoder = json.JSONDecoder()
    chunks = []
    for match in re.finditer(r'self\.__next_f\.push\(\s*', html):
        try:
            chunk, _ = decoder.raw_decode(html, match.end())
        except ValueError:
            continue
        if isinstance(chunk, list) and len(chunk) == 2 and chunk[0] == 1 and isinstance(chunk[1], str):
            chunks.append(chunk[1])
    flight = ''.join(chunks)
    for match in re.finditer(r'(?:^|\n)[0-9a-f]+:', flight):
        try:
            record, _ = decoder.raw_decode(flight, match.end())
        except ValueError:
            continue
        pending = [record]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if str(value.get('id', '')).lower() == expected_id and 'propertyDetails' in value:
                    return value
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
    return None


def parse_revoland_property(row, source_url=''):
    """Compose a post from public property fields, retaining the source description."""
    if not isinstance(source_url, str):
        raise ValueError('Link nguồn của tin Revoland cần là văn bản.')
    expected_id = revoland_property_id(source_url)
    if expected_id and str(row.get('id', '')).lower() != expected_id:
        raise ValueError('JSON trả về khác mã tin trong link Revoland. Hãy kiểm tra lại nguồn.')
    title = row.get('title') or row.get('name') or ''
    description = row.get('description') or ''
    if not isinstance(title, str) or not isinstance(description, str):
        raise ValueError('Tiêu đề và mô tả của tin Revoland cần là văn bản.')
    title, description = clean_post_html(title).strip(), clean_post_html(description).strip()
    if not title or not description:
        raise ValueError('Tin Revoland cần có tiêu đề và mô tả.')
    details = row.get('propertyDetails') or {}
    price = row.get('priceDetails') or {}
    location = row.get('location') or {}
    if not isinstance(details, dict) or not isinstance(price, dict) or not isinstance(location, (dict, str)):
        raise ValueError('Thông tin chi tiết, giá hoặc vị trí của tin Revoland không đúng cấu trúc.')
    if isinstance(location, dict):
        location_text = location.get('address') or ', '.join(
            str(location[key]) for key in ('street', 'ward', 'district', 'city') if location.get(key))
    else:
        location_text = location
    if not isinstance(location_text, str):
        raise ValueError('Địa chỉ của tin Revoland cần là văn bản.')
    rental = row.get('transactionType') == 'ForRent'
    amount = _mongo_num(price.get('rentalPrice' if rental else 'salePrice'))
    price_text = 'Chưa có thông tin giá'
    if amount is not None and math.isfinite(amount) and amount > 0:
        currency = price.get('currency') or 'VND'
        divisor, unit = (1, currency)
        if currency == 'VND':
            divisor, unit = (1_000_000_000, 'tỷ') if amount >= 1_000_000_000 else (
                (1_000_000, 'triệu') if amount >= 1_000_000 else (1, 'đ'))
        number = format(Decimal(str(amount)) / Decimal(divisor), 'f')
        if '.' in number:
            number = number.rstrip('0').rstrip('.')
        price_text = f'{number.replace(".", ",")} {unit}' + ('/tháng' if rental else '')
    lines = [f'🏡 {title}']
    if location_text:
        lines.append(f'📍 Vị trí: {location_text}')
    lines.append(f'💰 {"Giá thuê" if rental else "Giá bán"}: {price_text}')
    areas = []
    for key, label in (('landArea', 'Diện tích đất'), ('buildingArea', 'Diện tích xây dựng'),
                       ('usableArea', 'Diện tích sử dụng')):
        value = _mongo_num(details.get(key))
        if value is not None and math.isfinite(value) and value > 0:
            areas.append(value)
            lines.append(f'📐 {label}: {value:g} m²')
    rooms = {}
    for key, label in (('bedrooms', 'Phòng ngủ'), ('bathrooms', 'WC')):
        value = _mongo_num(details.get(key))
        rooms[key] = int(value) if value is not None and math.isfinite(value) and value > 0 and value.is_integer() else None
        if rooms[key]:
            lines.append(f'{label}: {rooms[key]}')
    code = str(row.get('propertyCode') or row.get('code') or '').strip()
    if code:
        lines.append(f'Mã tin: {code}')
    lines.extend(('', description))
    images = row.get('imageUrls') or []
    if not isinstance(images, list) or any(not isinstance(image, str) for image in images):
        raise ValueError('imageUrls của tin Revoland cần là danh sách link ảnh.')
    if revoland_property_id(source_url):
        source_url = urlunsplit(urlsplit(source_url)._replace(query='', fragment=''))
    status = 'published'
    if str(row.get('status') or 'PUBLISH').upper() not in ('PUBLISH', 'PUBLISHED', 'ACTIVE', 'AVAILABLE'):
        status = 'unavailable'
    if str(row.get('commercialStatus') or '').upper() in ('SOLD', 'RENTED'):
        status = 'sold'
    return {
        'title': title, 'description': description, 'post_text': '\n'.join(lines),
        'price_text': price_text, 'location': location_text or '',
        'area_m2': areas[0] if areas else None, **rooms,
        'property_type': _QUINLAND_TYPE_LABELS.get(str(row.get('type') or ''), 'Bất động sản'),
        'source_url': source_url, 'revoland_url': source_url or None, 'code': code,
        'media_urls': [urljoin(source_url, image.strip()) for image in images if image.strip()],
        'status': status,
    }


def _mongo_num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ('$numberLong', '$numberInt', '$numberDouble', '$numberDecimal'):
            if key in value:
                try:
                    return float(value[key])
                except (TypeError, ValueError):
                    return None
    return None


def _fmt_vn_num(val: float) -> str:
    text = f'{val:.2f}'.rstrip('0').rstrip('.')
    return text.replace('.', ',')


def _format_quinland_price(price_details: dict, tx_type: str) -> str:
    sale = _mongo_num(price_details.get('salePrice')) or 0.0
    rent = _mongo_num(price_details.get('rentalPrice')) or 0.0
    if tx_type == 'ForRent' and rent > 0:
        if rent >= 1_000_000_000:
            return f'{_fmt_vn_num(rent / 1_000_000_000)} tỷ/tháng'
        if rent >= 1_000_000:
            return f'{_fmt_vn_num(rent / 1_000_000)} triệu/tháng'
        return f'{int(rent):,} đ/tháng'.replace(',', '.')
    amount = sale if sale > 0 else rent
    if amount >= 1_000_000_000:
        return f'{_fmt_vn_num(amount / 1_000_000_000)} tỷ'
    if amount >= 1_000_000:
        return f'{_fmt_vn_num(amount / 1_000_000)} triệu'
    return 'Thương lượng'


# HTML from rich-text exports must become plain Facebook post text, while
# ordinary text (including line endings and mathematical < > signs) stays intact.
_POST_TAGS = frozenset(('p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u', 's',
    'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre',
    'section', 'article', 'header', 'footer', 'table', 'thead', 'tbody', 'tr', 'td', 'th',
    'hr', 'img', 'font', 'small', 'sup', 'sub', 'script', 'style', 'iframe', 'noscript'))
_POST_BLOCKS = frozenset(('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
    'pre', 'section', 'article', 'header', 'footer', 'ul', 'ol', 'table', 'thead', 'tbody'))
_POST_HIDDEN = frozenset(('script', 'style', 'iframe', 'noscript'))
_POST_TAG_RE = re.compile(r'</?(' + '|'.join(sorted(_POST_TAGS)) + r')(?=[\s/>])[^>]*>', re.I)


class PostTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in _POST_HIDDEN:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag in _POST_BLOCKS:
            self.parts.append('\n\n')
        elif tag in ('br', 'hr', 'tr'):
            self.parts.append('\n')
        elif tag == 'li':
            self.parts.append('\n- ')
        elif tag in ('td', 'th'):
            self.parts.append(' ')
        elif tag not in _POST_TAGS:
            self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if tag not in _POST_HIDDEN:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.hidden:
            if tag in self.hidden:
                del self.hidden[self.hidden.index(tag):]
            return
        if tag in _POST_BLOCKS:
            self.parts.append('\n\n')
        elif tag == 'tr':
            self.parts.append('\n')
        elif tag not in _POST_TAGS:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_post_html(value: str) -> str:
    decoded = value
    # Rich-text exports can also encode the markup itself as &lt;br&gt;.
    for _ in range(2):
        expanded = re.sub(r'&(?:#[xX][0-9a-fA-F]+|#[0-9]+|[a-zA-Z][a-zA-Z0-9]+);',
                          lambda match: unescape(match.group()), decoded)
        if expanded == decoded:
            break
        decoded = expanded
    if not _POST_TAG_RE.search(decoded):
        return decoded.replace('\xa0', ' ')
    parser = PostTextParser()
    parser.feed(decoded)
    parser.close()
    result = ''.join(parser.parts).replace('\xa0', ' ')
    result = result.replace('\r\n', '\n').replace('\r', '\n')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in result.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _clean_quinland_description(raw_desc: str) -> str:
    cleaned_lines = []
    for line in (raw_desc or '').splitlines():
        stripped = line.strip()
        if not stripped:
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            continue
        if re.match(r'^(liên hệ|lh|call|zalo|hotline)\b', stripped, flags=re.I) and _PHONE_RE.search(stripped):
            continue
        cleaned_lines.append(_PHONE_RE.sub('[SĐT liên hệ]', stripped))
    while cleaned_lines and cleaned_lines[-1] == '':
        cleaned_lines.pop()
    body = '\n'.join(cleaned_lines).strip()
    cta = '📩 Anh/chị quan tâm vui lòng bình luận hoặc nhắn tin trực tiếp để nhận thông tin chi tiết và hẹn xem thực tế!'
    return f'{body}\n\n{cta}' if body else cta


def parse_quinland_record(row: dict, index: int = 0) -> dict:
    raw_id = row.get('_id')
    oid = str(raw_id.get('$oid') if isinstance(raw_id, dict) else (raw_id or f'idx_{index}')).strip()
    tx_type = str(row.get('transactionType') or 'ForSale')
    tx_label = 'Cho thuê' if tx_type == 'ForRent' else 'Bán'
    prop_type = _QUINLAND_TYPE_LABELS.get(str(row.get('type') or ''), 'Bất động sản')
    details = row.get('propertyDetails') or {}
    price_details = row.get('priceDetails') or {}
    loc = row.get('location') or {}

    loc_parts = []
    for part in (loc.get('address'), loc.get('ward'), loc.get('district'), loc.get('city')):
        p = str(part or '').strip(' ,-')
        if p and not any(p.lower() in existing.lower() or existing.lower() in p.lower() for existing in loc_parts):
            loc_parts.append(p)
    location = ', '.join(loc_parts) or 'TP. Hồ Chí Minh'

    area = _mongo_num(details.get('buildingArea')) or _mongo_num(details.get('landArea'))
    area_m2 = round(area, 2) if area and area > 0 else None
    beds = _mongo_num(details.get('bedrooms'))
    baths = _mongo_num(details.get('bathrooms'))
    bedrooms = int(beds) if beds and beds > 0 else None
    bathrooms = int(baths) if baths and baths > 0 else None

    raw_title = _PHONE_RE.sub('', str(row.get('title') or '').strip()).strip(' -–|')
    if not raw_title or len(raw_title) < 22 or not re.search(r'\b(bán|thuê|căn hộ|nhà|đất)\b', raw_title, flags=re.I):
        suffix = f' — { raw_title }' if raw_title else ''
        short_loc = str(loc.get('ward') or loc.get('city') or 'TP.HCM').strip()
        title = f'{tx_label.upper()} {prop_type.upper()} tại {short_loc}{suffix}'
    else:
        title = raw_title

    price_text = _format_quinland_price(price_details, tx_type)
    description = _clean_quinland_description(str(row.get('description') or ''))
    images = [u.strip() for u in (row.get('images') or []) if isinstance(u, str) and u.strip()]
    return {
        'oid': oid,
        'index': index,
        'title': title[:500],
        'property_type': f'{tx_label} · {prop_type}',
        'tx_label': tx_label,
        'price_text': price_text,
        'area_m2': area_m2,
        'bedrooms': bedrooms,
        'bathrooms': bathrooms,
        'location': location[:500],
        'description': description[:49000],
        'images': images,
    }


class SourceListing(PropertyListing):
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    area_m2: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    property_type: str | None = None
    source_url: str = ''
    source_mode: str = 'live'
    imported_at: str = Field(default_factory=utc_now_iso)
    image_paths: list[str] = Field(default_factory=list)
    image_hashes: list[str] = Field(default_factory=list)
    image_errors: list[str] = Field(default_factory=list)
    pending_image_urls: list[str] = Field(default_factory=list)
    folder_name: str | None = Field(default=None, max_length=255)
    content_file: str | None = Field(default=None, max_length=255)
    post_text: str | None = None


def public_url(value, resolve=True):
    parts = urlsplit(str(value or '').strip())
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.port not in (None, 80, 443):
        raise ValueError('Nguồn/ảnh cần URL HTTP(S) công khai, không chứa tài khoản hoặc cổng riêng.')
    host_ascii = parts.hostname.encode('idna').decode('ascii')
    netloc = f'{host_ascii}:{parts.port}' if parts.port else host_ascii
    if resolve:
        try:
            addresses = socket.getaddrinfo(host_ascii, parts.port or (443 if parts.scheme == 'https' else 80))
        except OSError as exc:
            raise ValueError('Không phân giải được tên miền nguồn/ảnh.') from exc
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError('Không đọc địa chỉ nội bộ, loopback hoặc mạng riêng. Dùng nút nguồn demo để thử cục bộ.')
    safe_path = quote(unquote(parts.path or '/'), safe="/:@!$&'()*+,;=-._~")
    return urlunsplit((parts.scheme, netloc, safe_path, parts.query, ''))


def download_error_message(response):
    """Classify bounded error details without displaying remote HTML or secrets."""
    if response.headers.get('cf-mitigated', '').lower() == 'challenge':
        return ('Nguồn ảnh yêu cầu xác minh Cloudflare. Tool sẽ mở trình duyệt để tải ảnh; '
                'nếu vẫn lỗi, nhờ bên cung cấp dữ liệu gửi link ảnh công khai đang hoạt động.')
    prefix = bytearray()
    try:
        for chunk in response.iter_content(1024):
            if chunk:
                prefix.extend(chunk[:4096 - len(prefix)])
            if len(prefix) >= 4096:
                break
    except requests.RequestException:
        pass
    body = prefix.decode('utf-8', errors='replace').casefold()
    if 'userprojectaccountproblem' in body and ('closed' in body or 'disabled' in body):
        return ('Kho ảnh Google Cloud/Firebase bị khóa do tài khoản thanh toán đã đóng '
                'hoặc bị vô hiệu. Nhờ bên cung cấp dữ liệu khôi phục kho ảnh hoặc gửi '
                'ảnh/link ảnh khác đang hoạt động.')
    if is_cloudflare_block(response.status_code, response.headers, bytes(prefix)):
        return (f'Cloudflare chặn tải ảnh tự động (HTTP {response.status_code}). Tool sẽ mở trình duyệt để tải ảnh; '
                'nếu vẫn lỗi, nhờ bên cung cấp dữ liệu gửi link ảnh công khai.')
    if response.status_code in (401, 403):
        return (f'Nguồn/ảnh từ chối truy cập (HTTP {response.status_code}). '
                'Kiểm tra quyền truy cập hoặc nhờ bên cung cấp dữ liệu gửi link ảnh công khai.')
    return f'Nguồn/ảnh trả HTTP {response.status_code}; chưa nhập dữ liệu.'


def _blocked(response, message: str = '') -> bool:
    """Lỗi có thể vượt qua bằng trình duyệt thật: Cloudflare/WAF/chống bot/hotlink."""
    if response.headers.get('cf-mitigated', '').lower() == 'challenge' or 'Cloudflare' in message:
        return True
    if 'thanh toán đã đóng' in message:
        return False
    return response.status_code in (403, 429, 503)


def fetch_public(value, max_bytes=None, referer=None):
    """Tải URL công khai với header giống trình duyệt. ``max_bytes=None``: không giới hạn dung lượng."""
    last_error = None
    with requests.Session() as session:
        session.trust_env = False
        # Retry transient network/server failures; access denials retain their specific handling.
        adapter = HTTPAdapter(max_retries=Retry(
            total=2, connect=2, read=2, status=2, backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504), allowed_methods=('GET',),
            respect_retry_after_header=False, raise_on_status=False,
        ))
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        # Thử với Referer (chống hotlink), sau đó thử lại không Referer trước khi báo lỗi.
        for ref in ([referer, None] if referer else [None]):
            current = value
            for _ in range(10):
                current = public_url(current)
                try:
                    with session.get(current, timeout=(10, 60), stream=True, allow_redirects=False,
                                     headers=browser_headers(current, ref)) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            current = urljoin(current, response.headers.get('Location', ''))
                            continue
                        if response.status_code != 200 or response.headers.get('cf-mitigated', '').lower() == 'challenge':
                            message = download_error_message(response)
                            blocked = _blocked(response, message)
                            last_error = BlockedDownloadError(message) if blocked else ValueError(message)
                            break
                        content = bytearray()
                        for chunk in response.iter_content(65536):
                            content.extend(chunk)
                            if max_bytes is not None and len(content) > max_bytes:
                                raise ValueError('Nguồn hoặc ảnh vượt giới hạn dung lượng.')
                        return bytes(content), current, response.headers.get('Content-Type', '')
                except requests.RequestException as exc:
                    logging.getLogger(__name__).warning('Image download failed (%s)', type(exc).__name__, exc_info=True)
                    raise ValueError(f'Không tải được nguồn/ảnh ({type(exc).__name__}). Kiểm tra kết nối hoặc quyền truy cập website.') from exc
            else:
                raise ValueError('Nguồn/ảnh chuyển hướng quá nhiều lần.')
    raise last_error


class JsonLdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.buffer = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.active = True
            self.buffer = []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.active = False
            try:
                self.documents.append(json.loads(''.join(self.buffer)))
            except json.JSONDecodeError:
                pass  # Other valid property blocks may exist on the page.


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text(value):
    parser = PlainText()
    parser.feed(str(value or ''))
    return ' '.join(' '.join(parser.parts).split())


def structured_properties(html, base_url):
    parser = JsonLdParser()
    parser.feed(html)
    found = []
    def visit(node):
        if isinstance(node, list):
            for row in node: visit(row)
        elif isinstance(node, dict):
            types = node.get('@type', [])
            types = [types] if isinstance(types, str) else types if isinstance(types, list) else []
            if {t for t in types if isinstance(t, str)}.intersection({'RealEstateListing', 'Apartment', 'House', 'Residence', 'SingleFamilyResidence'}):
                offers = node.get('offers', {})
                offers = offers[0] if isinstance(offers, list) and offers else offers
                offers = offers if isinstance(offers, dict) else {}
                item = offers.get('itemOffered', node.get('about', node))
                item = item if isinstance(item, dict) else node
                title = text(node.get('name') or node.get('headline') or item.get('name'))
                description = text(node.get('description') or item.get('description'))
                if title and description:
                    address = item.get('address', node.get('address'))
                    if isinstance(address, dict):
                        address = ', '.join(str(address[k]) for k in ('streetAddress', 'addressLocality', 'addressRegion', 'addressCountry') if isinstance(address.get(k), str))
                    images = node.get('image', item.get('image', []))
                    images = images if isinstance(images, list) else [images]
                    images = [image.get('url') or image.get('contentUrl') if isinstance(image, dict) else image for image in images]
                    price = offers.get('price')
                    if not isinstance(price, (str, int, float)):
                        price = None
                    price_text = f"{price} {offers.get('priceCurrency', '')}".strip() if price is not None else 'Chưa có thông tin giá'
                    # A floorSize in square feet must not be silently labeled m².
                    floor = item.get('floorSize', {})
                    area = floor.get('value') if isinstance(floor, dict) and floor.get('unitCode') == 'MTK' else None
                    found.append({'title': title, 'description': description, 'price_text': price_text,
                        'location': text(address) or 'Chưa có thông tin vị trí', 'area_m2': area,
                        'media_urls': [urljoin(base_url, image) for image in images if isinstance(image, str) and image],
                        'source_url': urljoin(base_url, node['url'] if isinstance(node.get('url'), str) else base_url),
                        'status': 'sold' if str(offers.get('availability', '')).endswith(('SoldOut', 'OutOfStock')) else 'published'})
                return
            for value in node.values():
                if isinstance(value, (dict, list)): visit(value)
    for document in parser.documents: visit(document)
    return found


DEMO_PROPERTIES = [
    {'title': 'DỮ LIỆU MẪU — Căn hộ 2 phòng ngủ', 'description': 'Tin và ảnh minh họa để thử luồng lấy tin, preview và chiến dịch. Không phải tin rao bán thực tế.',
     'price_text': '2,5 tỷ (giá minh họa)', 'location': 'Khu vực mẫu', 'area_m2': 65,
     'media_urls': ['https://demo.invalid/image1.png'], 'source_url': 'https://demo.invalid/can-ho-01', 'status': 'published'},
    {'title': 'DỮ LIỆU MẪU — Nhà phố', 'description': 'Tin mẫu thứ hai. Bộ dữ liệu này không được gửi lên Facebook.',
     'price_text': 'Chưa có thông tin giá', 'location': 'Chưa có thông tin vị trí',
     'media_urls': [], 'source_url': 'https://demo.invalid/nha-pho-02', 'status': 'published'},
]


def demo_html():
    payload = [{'@context': 'https://schema.org', '@type': 'RealEstateListing', 'name': r['title'],
                'description': r['description'], 'url': r['source_url']} for r in DEMO_PROPERTIES]
    cards = ''.join(f'<article><h2>{r["title"]}</h2><p>{r["description"]}</p></article>' for r in DEMO_PROPERTIES)
    return '<!doctype html><meta charset="utf-8"><title>Website BĐS demo</title><h1>Website BĐS mẫu — không phải tin thật</h1>' + cards + '<script type="application/ld+json">' + json.dumps(payload, ensure_ascii=False) + '</script>'


class WebsiteSourceService:
    def __init__(self, root=None, quinland_file=None):
        self.root = Path(root or RUNTIME_DIR / 'data' / 'website_sources')
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'sources.sqlite3'
        self.quinland_file = Path(quinland_file) if quinland_file else (ROOT_DIR / 'resources' / 'datasets' / 'quinland.json')
        self._quinland_cache = None
        self._image_load_lock = threading.Lock()
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS listings (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.commit()

    def _load_quinland_rows(self) -> list[dict]:
        if self._quinland_cache is not None:
            return self._quinland_cache
        candidate = self.quinland_file
        if not candidate.is_file():
            raise ValueError('Không tìm thấy dữ liệu resources/datasets/quinland.json.')
        raw = json.loads(candidate.read_text(encoding='utf-8-sig'))
        if not isinstance(raw, list):
            raise ValueError('File dữ liệu QuinLand không đúng định dạng mảng JSON.')
        self._quinland_cache = [
            parse_quinland_record(row, idx)
            for idx, row in enumerate(raw)
            if isinstance(row, dict) and not row.get('isDeleted')
        ]
        return self._quinland_cache

    def list_quinland_catalog(self, query: str = '', limit: int = 80) -> list[dict]:
        try:
            rows = self._load_quinland_rows()
        except ValueError:
            return []
        q = (query or '').strip().lower()
        if q:
            rows = [
                r for r in rows
                if q in r['title'].lower() or q in r['location'].lower()
                or q in r['property_type'].lower() or q in r['price_text'].lower()
            ]
        return [
            {
                'oid': r['oid'],
                'index': r['index'],
                'title': r['title'],
                'property_type': r['property_type'],
                'price_text': r['price_text'],
                'area_m2': r['area_m2'],
                'bedrooms': r['bedrooms'],
                'bathrooms': r['bathrooms'],
                'location': r['location'],
                'image_count': len(r['images']),
            }
            for r in rows[:max(1, min(limit, 250))]
        ]

    def import_quinland(self, record_ids: list[str] | None = None, max_images: int = 4) -> list[SourceListing]:
        catalog = self._load_quinland_rows()
        if record_ids:
            wanted = {str(x).strip() for x in record_ids if str(x).strip()}
            selected = [r for r in catalog if r['oid'] in wanted or str(r['index']) in wanted]
        else:
            by_idx = {r['index']: r for r in catalog}
            selected = [by_idx[i] for i in QUINLAND_DEFAULT_INDICES if i in by_idx]
            if not selected:
                selected = catalog[:6]
        if not selected:
            raise ValueError('Không tìm thấy bài tin phù hợp trong dữ liệu QuinLand.')
        if len(selected) > 15:
            raise ValueError('Mỗi lần nạp tối đa 15 bài từ kho QuinLand để tải ảnh nhanh và ổn định.')

        max_images = max(1, min(int(max_images), 12))
        prepared = []
        for item in selected:
            identity = 'ql_' + re.sub(r'[^a-zA-Z0-9_-]', '', item['oid'])[:36]
            existing = self.get_listing_by_id(identity)
            if existing and existing.image_paths and all(
                Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == h
                for p, h in zip(existing.image_paths, existing.image_hashes)
            ):
                prepared.append(existing)
                continue

            folder = self.root / 'images' / uuid.uuid4().hex
            folder.mkdir(parents=True, exist_ok=True)
            image_paths, image_hashes, media_urls = [], [], []
            for image_url in item['images'][:max_images]:
                try:
                    raw, _, _ = fetch_public(image_url, None)
                    path = folder / f'{len(image_paths)}.jpg'
                    digest = save_image_snapshot(raw, path)
                    image_paths.append(str(path))
                    image_hashes.append(digest)
                    media_urls.append(image_url)
                except Exception:
                    continue

            listing = SourceListing(
                id=identity,
                code=f"QL-{item['index'] + 1:03d}",
                title=item['title'],
                property_type=item['property_type'],
                description=item['description'],
                price_text=item['price_text'],
                location=item['location'],
                area_m2=item['area_m2'],
                bedrooms=item['bedrooms'],
                bathrooms=item['bathrooms'],
                source_url='',
                source_mode='live',
                status='published',
                media_urls=media_urls or [f'local://photo/{i}' for i in range(len(image_paths))],
                image_paths=image_paths,
                image_hashes=image_hashes,
                imported_at=utc_now_iso(),
            )
            prepared.append(listing)

        with closing(sqlite3.connect(self.db_path)) as db:
            with db:
                for listing in prepared:
                    db.execute(
                        'INSERT INTO listings VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                        (listing.id, listing.model_dump_json()),
                    )
        return prepared

    def list_listings(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            rows = db.execute('SELECT body FROM listings ORDER BY rowid DESC').fetchall()
        return [SourceListing.model_validate_json(row[0]) for row in rows]

    def get_listing_by_id(self, listing_id):
        with closing(sqlite3.connect(self.db_path)) as db:
            row = db.execute('SELECT body FROM listings WHERE id=?', (listing_id,)).fetchone()
        return SourceListing.model_validate_json(row[0]) if row else None

    def import_demo(self):
        # Exercise the same HTML parser, then restore explicit demo-only fields.
        rows = structured_properties(demo_html(), 'https://demo.invalid/')
        for row, sample in zip(rows, DEMO_PROPERTIES): row.update(sample)
        return self._store(rows, 'mock')

    def import_url(self, url):
        body, final_url, content_type = fetch_public(url, None)
        expected_id = revoland_property_id(url)
        if expected_id and revoland_property_id(final_url) != expected_id:
            raise ValueError('Link Revoland chuyển sang tin khác. Hãy kiểm tra lại đường dẫn.')
        try:
            decoded = body.decode('utf-8-sig')
        except UnicodeError as exc:
            raise ValueError('Nguồn cần mã hóa UTF-8.') from exc
        if 'json' in content_type or decoded.lstrip().startswith(('[', '{')):
            try:
                payload = json.loads(decoded)
            except json.JSONDecodeError as exc:
                raise ValueError('JSON nguồn không hợp lệ.') from exc
            if isinstance(payload, dict) and payload.get('status') is False:
                raise ValueError('Nguồn JSON báo lấy tin không thành công.')
            rows = payload.get('listings', payload.get('data')) if isinstance(payload, dict) else payload
            if isinstance(payload, dict) and 'propertyDetails' in payload:
                rows = payload
            if isinstance(rows, dict) and 'propertyDetails' in rows:
                rows = [rows]
            if not isinstance(rows, list):
                raise ValueError('API cần mảng tin hoặc object listings/data chứa tin bất động sản.')
            rows = [parse_revoland_property(row, final_url if expected_id else row.get('source_url') or final_url)
                    if isinstance(row, dict) and 'propertyDetails' in row and ('imageUrls' in row or 'id' in row) else row
                    for row in rows]
            if any(not isinstance(r, dict) or not isinstance(r.get('source_url', final_url), str) or not isinstance(r.get('media_urls', []), list)
                   or any(not isinstance(image, str) for image in r.get('media_urls', [])) for r in rows):
                raise ValueError('Mỗi tin cần là object; media_urls cần là mảng URL dạng chuỗi.')
            rows = [{**r, 'source_url': urljoin(final_url, r.get('source_url') or final_url),
                     'media_urls': [urljoin(final_url, image) for image in r.get('media_urls', [])]} for r in rows if isinstance(r, dict)]
        else:
            expected_id = revoland_property_id(final_url)
            property_data = revoland_page_property(decoded, expected_id) if expected_id else None
            rows = [parse_revoland_property(property_data, final_url)] if property_data else structured_properties(decoded, final_url)
            if expected_id:
                rows = [row for row in rows if revoland_property_id(row.get('source_url', '')) == expected_id]
        if not rows:
            raise ValueError('Không nhận diện được tin. Chỉ hỗ trợ JSON theo mẫu hoặc HTML có JSON-LD BĐS; website cần đăng nhập/JavaScript cần adapter riêng.')
        for row in rows:
            row['media_urls'] = [public_url(image, resolve=False) for image in row.get('media_urls', [])]
        return self._store(rows, 'live')

    def import_manual(self, title, description, price_text='', location='', area_m2=None, images_base64=(),
                      *, folder_name=None, content_file=None, post_text=None):
        """Lưu tin người dùng tự soạn trực tiếp và chuẩn hóa ảnh chọn từ máy tính."""
        title = (title or '').strip()
        description = (description or '').strip()
        price_text = (price_text or '').strip()
        location = (location or '').strip()
        if not title or not description or len(title) > 512 or len(description) > 50000:
            raise InputError('Tin cần tiêu đề (tối đa 512 ký tự) và nội dung mô tả (tối đa 50.000 ký tự).', 'title' if not title or len(title) > 512 else 'description')
        if len(images_base64) > 12:
            raise InputError('Mỗi tin tối đa 12 ảnh.', 'images_base64')
        identity = 'manual_' + hashlib.sha256(f'{title}\n{price_text}\n{location}\n{description}'.encode()).hexdigest()[:32]
        if folder_name is not None:
            identity = 'folder_' + hashlib.sha256(f'{folder_name}\n{post_text}'.encode()).hexdigest()[:32]
        folder = self.root / 'images' / uuid.uuid4().hex
        folder.mkdir(parents=True)
        image_paths, image_hashes = [], []
        for index, encoded in enumerate(images_base64):
            payload = encoded.split(',', 1)[1] if ',' in encoded and encoded.lstrip().startswith('data:') else encoded
            try:
                raw = base64.b64decode(payload, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise InputError(f'Ảnh số {index + 1} không đọc được. Vui lòng chọn lại file ảnh JPG/PNG.', 'images_base64', location=['images_base64', index]) from exc
            if len(raw) > 20 * 1024 * 1024:
                raise InputError(f'Ảnh số {index + 1} vượt 20 MB.', 'images_base64', location=['images_base64', index])
            path = folder / f'{index}.jpg'
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width * image.height > 25000000:
                        raise ValueError('Ảnh vượt 25 megapixel.')
                    ImageOps.exif_transpose(image).convert('RGB').save(path, 'JPEG', quality=95)
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                raise InputError(f'Ảnh số {index + 1} không hợp lệ hoặc quá lớn; vui lòng chọn ảnh JPG/PNG khác.', 'images_base64', location=['images_base64', index]) from exc
            image_paths.append(str(path))
            image_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        listing = SourceListing(
            id=identity, code=identity[:12], title=title, description=description,
            price_text=price_text or 'Liên hệ', location=location or '',
            area_m2=area_m2, source_url='', source_mode='live', status='published',
            media_urls=[f'local://photo/{i}' for i in range(len(image_paths))],
            image_paths=image_paths, image_hashes=image_hashes, imported_at=utc_now_iso(),
            folder_name=folder_name, content_file=content_file, post_text=post_text,
        )
        with closing(sqlite3.connect(self.db_path)) as db:
            with db:
                db.execute('INSERT INTO listings VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                           (listing.id, listing.model_dump_json()))
        return [listing]

    def import_json(self, payload, base_dir=None, defer_images=False):
        """Nạp bài từ file JSON: giữ nguyên nội dung, tải ảnh (không giới hạn số bài/số ảnh/độ dài).

        Ảnh có thể là link HTTP(S) (kể cả sau Cloudflare), ảnh base64 ``data:image/...`` hoặc
        đường dẫn file trên máy. Ảnh nào tải lỗi được ghi vào ``image_errors`` của bài, các ảnh
        còn lại vẫn được nạp để người dùng tự quyết định khi xem trước.
        """
        if isinstance(payload, dict):
            if payload.get('status') is False:
                raise InputError('JSON báo lấy tin không thành công.', 'data')
            wrapped = next((payload[key] for key in ('posts', 'listings', 'data', 'items', 'records', 'results')
                            if isinstance(payload.get(key), list)), None)
            if wrapped is not None:
                payload = wrapped
            elif isinstance(payload.get('data'), dict) and 'propertyDetails' in payload['data']:
                payload = [payload['data']]
            elif any(isinstance(payload.get(key), str) for key in _CONTENT_KEYS) or any(
                key in payload for key in ('propertyDetails', 'priceDetails')
            ):
                payload = [payload]
            else:
                payload = None
        if not isinstance(payload, list) or not payload:
            raise InputError('File JSON cần chứa ít nhất một bài đăng (mảng bài hoặc object có posts/listings/data).', 'data', hint='Chọn file JSON có nội dung bài đăng, sau đó nạp lại.')
        rows = []
        for index, row in enumerate(payload, 1):
            if not isinstance(row, dict):
                raise InputError(f'Bài {index}: dữ liệu bài cần là một object.', 'data', location=['data', index - 1])
            if row.get('isDeleted') is True and len(payload) > 1:
                continue
            direct_keys = ('content', 'post_text', 'text', 'message', 'body', 'caption')
            direct_content = next(
                (row[key] for key in direct_keys if isinstance(row.get(key), str) and row[key].strip()),
                None,
            )
            url_raw = row.get('source_url') or row.get('url') or ''
            url = ''
            if isinstance(url_raw, str) and url_raw.strip():
                candidate_url = url_raw.strip()
                if candidate_url.lower().startswith('www.'):
                    candidate_url = 'https://' + candidate_url
                try:
                    url = public_url(candidate_url, resolve=False)
                except ValueError:
                    url = ''
            if direct_content is None and 'propertyDetails' in row and ('imageUrls' in row or 'id' in row):
                try:
                    rows.append(parse_revoland_property(row, url))
                except ValueError as exc:
                    raise InputError(f'Bài {index}: {exc}', 'data', location=['data', index - 1]) from exc
                continue
            if direct_content is None and any(k in row for k in ('propertyDetails', 'priceDetails', 'transactionType')):
                parsed = parse_quinland_record(row, index - 1)
                refs = [normalize_image_ref(u, url) for u in parsed['images']]
                rows.append({
                    'title': parsed['title'],
                    'property_type': parsed['property_type'],
                    'description': parsed['description'],
                    'post_text': None,
                    'price_text': parsed['price_text'],
                    'location': parsed['location'],
                    'area_m2': parsed['area_m2'],
                    'bedrooms': parsed['bedrooms'],
                    'bathrooms': parsed['bathrooms'],
                    'source_url': url,
                    'media_urls': refs,
                })
                continue
            content = direct_content
            if content is None and isinstance(row.get('description'), str) and row['description'].strip():
                content = row['description']
            if content is None:
                raise InputError(f'Bài {index}: thiếu nội dung bài (trường content).', 'data', location=['data', index - 1, 'content'], hint='Bổ sung nội dung cho bài này trong file JSON rồi nạp lại.')
            title = row.get('title')
            if not isinstance(title, str) or not title.strip():
                title = next(line.strip() for line in content.splitlines() if line.strip())[:200]
            image_key = next((key for key in _IMAGE_KEYS if key in row and row[key] is not None), None)
            images = row[image_key] if image_key else []
            image_field = image_key or 'images'
            if isinstance(images, str):
                stripped_img = images.strip()
                if not stripped_img:
                    images = []
                elif stripped_img.lower().startswith('data:'):
                    images = [stripped_img]
                else:
                    images = [s for s in re.split(r'[\r\n]+|,\s*(?=https?://)', stripped_img) if s.strip()]
            elif isinstance(images, dict):
                images = [images]
            if not isinstance(images, list):
                raise InputError(f'Bài {index}: ảnh cần là danh sách đường dẫn ảnh.', 'data', location=['data', index - 1, image_field])
            refs = []
            for image_index, item in enumerate(images):
                if item is None:
                    continue
                if isinstance(item, dict):
                    item = next((item[k] for k in ('url', 'src', 'href', 'link', 'image', 'path') if isinstance(item.get(k), str)), None)
                    if item is None:
                        continue
                if not isinstance(item, str):
                    raise InputError(f'Bài {index}: mỗi ảnh cần là chuỗi đường dẫn (hoặc object có url).', 'data', location=['data', index - 1, image_field, image_index])
                if item.strip():
                    refs.append(normalize_image_ref(item, url))
            rows.append({'title': title.strip(), 'description': content, 'post_text': content,
                         'price_text': '', 'location': '', 'source_url': url, 'media_urls': refs})
        if not rows:
            raise InputError('File JSON không có bài đăng hợp lệ.', 'data')
        return self._store(rows, 'live', allow_local=True, base_dir=base_dir, defer_images=defer_images)

    def _store(self, rows, mode, allow_local=False, base_dir=None, defer_images=False):
        prepared = []
        identities = set()
        for row in rows:
            if allow_local:
                url = row.get('source_url') or ''
                fingerprint = json.dumps(row, ensure_ascii=False, sort_keys=True).encode('utf-8')
                identity = 'json_' + hashlib.sha256(fingerprint).hexdigest()[:32]
            else:
                url = public_url(row.get('source_url', ''), resolve=mode != 'mock')
                identity = 'web_' + hashlib.sha256(url.encode()).hexdigest()[:32]
            if identity in identities:
                if allow_local:
                    continue  # Bài trùng lặp trong cùng file JSON: chỉ giữ một bản.
                raise ValueError('Mỗi tin cần source_url riêng; dữ liệu chứa bài trùng lặp hoặc trùng URL.')
            identities.add(identity)
            listing = SourceListing(**{**row, 'id': identity, 'code': row.get('code') or identity[:12], 'source_url': url,
                'source_mode': mode, 'image_paths': [], 'image_hashes': [], 'image_errors': [],
                'imported_at': utc_now_iso(), 'status': row.get('status', 'published')})
            if not listing.title.strip() or not listing.description.strip():
                raise ValueError('Mỗi tin cần có tiêu đề và nội dung.')
            prepared.append(listing)

        # Same JSON identity means unchanged content and image references. Reuse
        # complete snapshots instead of downloading them again on every import.
        to_download = []
        cached = {}
        if allow_local:
            with closing(sqlite3.connect(self.db_path)) as db:
                for offset in range(0, len(prepared), 400):
                    ids = [post.id for post in prepared[offset:offset + 400]]
                    placeholders = ','.join('?' for _ in ids)
                    cached.update(db.execute(f'SELECT id, body FROM listings WHERE id IN ({placeholders})', ids))
        for index, listing in enumerate(prepared):
            previous = cached.get(listing.id)
            existing = SourceListing.model_validate_json(previous) if previous else None
            if (existing and not existing.pending_image_urls and not existing.image_errors
                    and len(existing.image_paths) == len(listing.media_urls)
                    and len(existing.image_hashes) == len(existing.image_paths)
                    and all(Path(path).is_file() for path in existing.image_paths)):
                prepared[index] = existing
            elif defer_images:
                listing.pending_image_urls = listing.media_urls
                listing.media_urls = []
            else:
                to_download.append(listing)
        self._download_snapshots(to_download, mode, base_dir)

        with closing(sqlite3.connect(self.db_path)) as db:
            with db:
                for listing in prepared:
                    db.execute('INSERT INTO listings VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                               (listing.id, listing.model_dump_json()))
        return prepared

    def _download_snapshots(self, prepared, mode='live', base_dir=None):
        # Save each small batch before downloading more; a large export must not
        # retain thousands of full-resolution images in memory at the same time.
        jobs = [(post, index, ref) for post in prepared for index, ref in enumerate(post.media_urls)]
        kept = {post.id: [] for post in prepared}
        folders = {}
        for offset in range(0, len(jobs), IMAGE_DOWNLOAD_BATCH_SIZE):
            batch = jobs[offset:offset + IMAGE_DOWNLOAD_BATCH_SIZE]
            if mode == 'mock':
                sample = io.BytesIO()
                Image.new('RGB', (640, 400), '#bad8c7').save(sample, 'PNG')
                results = [(sample.getvalue(), None)] * len(batch)
            else:
                results = download_many([(ref, post.source_url or None) for post, _, ref in batch],
                                        fetch_public, base_dir=Path(base_dir) if base_dir else None)
            for (post, index, ref), (raw, error) in zip(batch, results):
                label = f'Ảnh {index + 1}'
                if raw is None:
                    post.image_errors.append(f'{label}: {error or "Không tải được ảnh."}')
                    continue
                folder = folders.get(post.id)
                if folder is None:
                    folder = folders[post.id] = self.root / 'images' / uuid.uuid4().hex
                    folder.mkdir(parents=True, exist_ok=True)
                path = folder / f'{len(post.image_paths)}.jpg'
                try:
                    digest = save_image_snapshot(raw, path)
                except Exception:  # noqa: BLE001 - dữ liệu không phải ảnh hoặc định dạng không hỗ trợ
                    path.unlink(missing_ok=True)
                    post.image_errors.append(f'{label}: Dữ liệu tải về không phải ảnh hoặc định dạng ảnh chưa hỗ trợ.')
                    continue
                post.image_paths.append(str(path))
                post.image_hashes.append(digest)
                kept[post.id].append(f'embedded://photo/{index}' if ref.lower().startswith('data:') else ref)
            del results
        for post in prepared:
            post.media_urls = kept[post.id]


    def load_listing_images(self, listing_id):
        # Serialize hydration, and condition the update on the original row so
        # a concurrent delete/reimport cannot be undone by a late download.
        with self._image_load_lock:
            with closing(sqlite3.connect(self.db_path)) as db:
                row = db.execute('SELECT body FROM listings WHERE id=?', (listing_id,)).fetchone()
            if not row:
                return None
            listing = SourceListing.model_validate_json(row[0])
            if not listing.pending_image_urls:
                return listing
            listing.media_urls = listing.pending_image_urls
            listing.pending_image_urls = []
            listing.image_paths, listing.image_hashes, listing.image_errors = [], [], []
            self._download_snapshots([listing])
            with closing(sqlite3.connect(self.db_path)) as db:
                with db:
                    updated = db.execute('UPDATE listings SET body=? WHERE id=? AND body=?',
                        (listing.model_dump_json(), listing_id, row[0])).rowcount
            return listing if updated else self.get_listing_by_id(listing_id)

    @staticmethod
    def listing_summary(listing):
        return {key: getattr(listing, key) for key in
                ('id', 'title', 'source_mode', 'price_text', 'folder_name')}

    def listing_catalog(self, query='', offset=0, limit=100, selected_id=''):
        offset, limit = max(0, offset), max(1, min(limit, 200))
        # Project only fields used by the selector; never transfer every post's
        # content and image arrays just to populate a list of titles.
        columns = ", ".join(f"json_extract(body, '$.{key}')" for key in
                            ('title', 'source_mode', 'price_text', 'folder_name'))
        where, params = '', []
        if query.strip():
            where = " WHERE instr(casefold(json_extract(body, '$.title')), ?) > 0"
            params = [query.strip().casefold()]
        with closing(sqlite3.connect(self.db_path)) as db:
            db.create_function('casefold', 1, lambda value: str(value or '').casefold())
            total = db.execute('SELECT count(*) FROM listings' + where, params).fetchone()[0]
            all_count = db.execute('SELECT count(*) FROM listings').fetchone()[0]
            rows = db.execute('SELECT id, ' + columns + ' FROM listings' + where +
                ' ORDER BY rowid DESC LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
        keys = ('id', 'title', 'source_mode', 'price_text', 'folder_name')
        selected = self.get_listing_by_id(selected_id) if selected_id else None
        return {'items': [dict(zip(keys, row)) for row in rows], 'total': total,
                'all_count': all_count, 'offset': offset, 'limit': limit,
                'selected': self.listing_summary(selected) if selected else None}

    def delete_listings(self, ids=(), delete_all=False):
        # Campaigns own references to the immutable image files. Keep those
        # files so deleting a source cannot break an already prepared campaign.
        with closing(sqlite3.connect(self.db_path)) as db:
            with db:
                if delete_all:
                    return db.execute('DELETE FROM listings').rowcount
                count = 0
                for listing_id in set(ids):
                    count += db.execute('DELETE FROM listings WHERE id=?', (listing_id,)).rowcount
                return count

    def provider(self, listing, selected_images):
        if len(set(selected_images)) != len(selected_images) or any(i < 0 or i >= len(listing.media_urls) for i in selected_images):
            raise InputError('Danh sách ảnh được chọn không hợp lệ.', 'image_indices')
        return SnapshotProvider(listing, selected_images)


class SnapshotProvider:
    def __init__(self, listing, indices):
        self.listing = listing
        self.indices = indices
        self.config = {'revoland_mock_mode': listing.source_mode != 'live'}

    def get_listing_by_id(self, listing_id):
        return self.listing if listing_id == self.listing.id else None

    def format_post_content(self, listing):
        return clean_post_html(self._format_raw_content(listing))

    def _format_raw_content(self, listing):
        if listing.post_text is not None:
            return listing.post_text
        if not listing.source_url:
            rooms = [
                *([f'{listing.bedrooms} Phòng ngủ'] if listing.bedrooms else []),
                *([f'{listing.bathrooms} WC'] if listing.bathrooms else []),
            ]
            room_suffix = f" ({', '.join(rooms)})" if rooms else ''
            specs = [
                *([f'🏷 Phân loại: {listing.property_type}'] if listing.property_type else []),
                *([f'💰 Giá: {listing.price_text}'] if listing.price_text and listing.price_text != 'Liên hệ' else []),
                *([f'📐 Diện tích: {listing.area_m2:g} m²{room_suffix}'] if listing.area_m2 is not None else ([f"🛏 Kết cấu: {', '.join(rooms)}"] if rooms else [])),
                *([f'📍 Vị trí: {listing.location}'] if listing.location else []),
            ]
            header = '\n'.join([f'🏡 {listing.title}', *specs])
            return f'{header}\n\n{listing.description}'
        return '\n'.join([listing.title, f'Giá: {listing.price_text}', f'Vị trí: {listing.location}',
            *([f'Diện tích: {listing.area_m2} m²'] if listing.area_m2 is not None else []),
            listing.description, 'Nguồn: ' + listing.source_url,
            'Vui lòng liên hệ để xác nhận tình trạng và thông tin hiện tại.'])

    def download_listing_images(self, listing):
        # CampaignService checks one saved file per selected URL. Integrity is
        # checked before reusing the immutable image files shown in preview.
        paths = []
        for index in self.indices:
            path = Path(listing.image_paths[index])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != listing.image_hashes[index]:
                raise InputError('Ảnh snapshot đã thay đổi. Nhập lại nguồn và xem trước lần nữa.', 'image_indices')
            paths.append(str(path))
        return paths
