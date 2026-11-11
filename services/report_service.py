"""Read-only reports: never log in, post to Facebook or create Revoland leads."""
import json
import re
from urllib.parse import urlsplit
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from core.filter_engine import RegistryFilterEngine
from core.contact_extractor import normalize_phone
from services.excel_exporter import export_records_to_excel, export_campaigns_to_excel, workbook_bytes

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_RECORDS = 5000


class CommentImportRecord(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, populate_by_name=True)
    id: str | None = Field(default=None, max_length=256)
    raw_content: str | None = Field(default=None, validation_alias=AliasChoices('raw_content', 'text'), max_length=20000)
    fb_user_name: str = Field(default='Khách hàng', validation_alias=AliasChoices('fb_user_name', 'author', 'customer_name'), max_length=256)
    listing_id: str | None = Field(default=None, max_length=256)
    campaign_id: str | None = Field(default=None, max_length=256)
    posting_task_id: str | None = Field(default=None, max_length=256)
    group_name: str | None = Field(default=None, max_length=512)
    listing_source_url: str | None = Field(default=None, max_length=2048)
    source_url: str | None = Field(default=None, max_length=2048)
    comment_url: str | None = Field(default=None, max_length=4096)
    fb_user_url: str | None = Field(default=None, max_length=2048)
    created_at: str | None = Field(default=None, max_length=64)
    revoland_lead_id: str | None = Field(default=None, max_length=256)
    sync_status: Literal['not_synced', 'synced', 'failed', 'unconfirmed'] = 'not_synced'
    phone_number: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=320)
    intent_summary: str | None = Field(default=None, max_length=4000)
    text_truncated: bool = False
    identity_status: Literal['known', 'anonymous', 'unknown'] = 'unknown'


def parse_comment_records(payload):
    if isinstance(payload, dict):
        payload = payload.get('records', payload.get('comments'))
    if not isinstance(payload, list):
        raise ValueError('JSON cần là mảng bình luận hoặc object có records/comments là mảng.')
    if len(payload) > MAX_IMPORT_RECORDS:
        raise ValueError('Mỗi lần chỉ nhận tối đa 5.000 bình luận.')
    try:
        records = TypeAdapter(list[CommentImportRecord]).validate_python(payload)
    except ValidationError as exc:
        raise ValueError('Bản ghi không hợp lệ. Bình luận tối đa 20.000 ký tự; xem file mẫu và độ dài các trường.') from exc
    for record in records:
        if record.raw_content is not None and not record.raw_content.strip():
            raise ValueError('Nội dung bình luận không được trống hoặc chỉ chứa khoảng trắng.')
        if record.raw_content is None and not any(
                value and value.strip() for value in (record.phone_number, record.email, record.revoland_lead_id)):
            raise ValueError('Bình luận cần text/raw_content; bản ghi lead cần phone_number, email hoặc revoland_lead_id.')
    return records


def load_comment_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError('File JSON vượt 5 MB.')
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('File cần là JSON hợp lệ, mã hóa UTF-8.') from exc
    return parse_comment_records(payload)


def prepare_comment_report(records, engine=None):
    engine = engine or RegistryFilterEngine()
    prepared = []
    for index, record in enumerate(records, 1):
        is_lead = record.raw_content is None
        result = engine.evaluate(record.raw_content or '')
        if record.text_truncated:
            result['interest_level'] = 'unclear'
            if result['classification'] == 'LEAD_POTENTIAL':
                result['classification'] = 'NEEDS_REVIEW'
            result['reasons'].insert(0, 'Nội dung có thể bị cắt ngắn; cần mở bình luận gốc để kiểm tra đầy đủ trước khi xác nhận lead.')
        if is_lead:
            result.update(classification='LEAD_POTENTIAL',score=0,
                reasons=[record.intent_summary or 'Lead nhập từ JSON; không có bình luận gốc để chấm điểm.'], interest_level='unclear')
        if record.phone_number:
            result['contacts']['primary_phone'] = normalize_phone(record.phone_number) or record.phone_number
        if record.email:
            result['contacts']['emails'] = [record.email]
        identity = record.identity_status
        if re.fullmatch(r'(?:anonymous (?:participant|member|user)|người (?:tham gia|dùng) ẩn danh|thành viên ẩn danh)(?:\s+\d+)?', record.fb_user_name.strip(), re.I):
            identity = 'anonymous'
        elif identity == 'unknown' and 'identity_status' not in record.model_fields_set and record.fb_user_name not in ('Khách hàng', 'Chưa xác định tác giả', 'Không rõ tên'):
            identity = 'known'
        channels = []
        for key, label in [('primary_phone', 'phone'), ('zalo', 'zalo'), ('emails', 'email')]:
            if result['contacts'].get(key):
                channels.append(label)
        def facebook_link(value):
            try:
                u = urlsplit(value or '')
                return u.scheme == 'https' and u.hostname in ('facebook.com', 'www.facebook.com', 'm.facebook.com') and not u.username
            except ValueError:
                return False
        if identity != 'anonymous' and facebook_link(record.fb_user_url):
            channels.append('profile')
        if facebook_link(record.comment_url):
            channels.append('comment')
        prepared.append({**record.model_dump(), 'id': record.id or f'CMT_{index:06d}',
            'record_type':'lead' if is_lead else 'comment',
            'classification': result['classification'], 'score': result['score'],
            'contacts': result['contacts'], 'reasons': result['reasons'], 'signals': result['signals'],
            'registry_version': result['registry_version'],
            'identity_status': identity, 'fb_user_url': None if identity == 'anonymous' else record.fb_user_url,
            'contact_channels': channels, 'interest_level': result.get('interest_level', 'unclear'),
            'interest_evidence': result.get('interest_evidence', [])})
    return prepared


def campaign_report_data(campaign_service, campaign_id=None):
    if campaign_id is None:
        return campaign_service.list_campaigns()
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign:
        raise ValueError('Không tìm thấy chiến dịch để xuất.')
    return [campaign]


def campaign_report_bytes(campaign_service, campaign_id=None):
    return workbook_bytes(export_campaigns_to_excel, campaign_report_data(campaign_service, campaign_id))


def comment_report_bytes(payload):
    records = prepare_comment_report(parse_comment_records(payload))
    return workbook_bytes(export_records_to_excel, records)


COMMENT_EXAMPLE = [
    {'id':'sample_001','author':'Khách mẫu A','text':'Dữ liệu thử: Cần mua căn này, cuối tuần xem nhà được không? SĐT 0912345678','listing_id':'can_mau_01'},
    {'id':'sample_002','author':'Khách mẫu B','text':'Cho mình xin giá với bạn.','listing_id':'can_mau_01'},
]
