"""FastAPI Server cho Tool Đăng Tin BĐS Lên Nhóm Facebook Bằng Phiên Trình Duyệt.
Cung cấp toàn bộ REST API điều hành theo đúng luồng người dùng:
1. Cấu hình & kiểm tra API Revoland
2. Lấy danh sách căn đã đăng trên Revoland
3. Đăng nhập & quản lý phiên Facebook (Playwright)
4. Quản lý danh sách nhóm Facebook
5. Tạo chiến dịch đăng bài, xem trước nội dung
6. Bấm đăng tự động, theo dõi kết quả từng nhóm, chống trùng & retry
"""
from __future__ import annotations

import hashlib
import os
from io import BytesIO
from pathlib import Path
import sys
from typing import Any, List, Optional
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import load_config, save_config
from build_info import BUILD_ID, BUILD_NAME
from services.campaign_service import CampaignService
from services.group_manager import GroupManager
from services.poster_engine import FacebookPosterEngine
from services.revoland_service import RevolandService, RevolandAPIError
from services.session_manager import FacebookSessionManager
from services.storage import ResourceBusyError
from services.input_errors import InputError
from services.report_service import campaign_report_bytes, comment_report_bytes, COMMENT_EXAMPLE, MAX_IMPORT_BYTES
from services.lead_filter_service import (LeadFilterService, filter_records, registry_inventory,
                                         select_customer_records, summarize_records)
from services.excel_exporter import export_records_to_excel, workbook_bytes
from services.website_source import WebsiteSourceService, demo_html, clean_post_html
from models.schema import GroupPostStatusEnum


app = FastAPI(
    title="Facebook Property Tool",
    description="Lấy tin bất động sản, đăng nhóm Facebook và lọc lead từ bình luận",
    version="4.0.0"
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])


@app.get('/api/app-info')
def get_app_info():
    return {'build_id': BUILD_ID, 'name': BUILD_NAME, 'input': 'link'}


@app.middleware('http')
async def protect_local_api(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Chỉ chấp nhận yêu cầu từ giao diện cùng địa chỉ.'}, status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('x-revoland-client') != 'local':
            return JSONResponse({'detail': 'Thiếu header X-Revoland-Client.'}, status_code=403)
        if request.url.path in ('/api/exports/comments', '/api/leads/filter') and request.method == 'POST':
            if len(await request.body()) > MAX_IMPORT_BYTES:
                return JSONResponse({'detail': 'Dữ liệu nhập vượt 5 MB.'}, status_code=413)
        if request.url.path == '/api/sources/manual' and request.method == 'POST':
            if len(await request.body()) > 40 * 1024 * 1024:
                return JSONResponse({'detail': 'Tổng dung lượng ảnh vượt giới hạn 40 MB.'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.exception_handler(RevolandAPIError)
async def revoland_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=502)


@app.exception_handler(ResourceBusyError)
async def busy_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.exception_handler(ValueError)
async def validation_error(request, exc):
    payload = {'detail': str(exc)}
    if isinstance(exc, InputError):
        payload['issues'] = [exc.issue()]
    return JSONResponse(payload, status_code=getattr(exc, 'status_code', 400))

@app.exception_handler(RequestValidationError)
async def request_validation_error(request, exc):
    messages = {'missing': 'Cần bổ sung thông tin này.', 'string_too_long': 'Nội dung vượt độ dài cho phép.',
                'string_too_short': 'Thông tin chưa đủ độ dài.', 'greater_than_equal': 'Giá trị nhỏ hơn mức cho phép.',
                'less_than_equal': 'Giá trị lớn hơn mức cho phép.', 'int_parsing': 'Cần nhập một số nguyên.',
                'float_parsing': 'Cần nhập một giá trị số.'}
    issues = []
    for error in exc.errors():
        loc = list(error.get('loc', ()))
        field = str(loc[1]) if len(loc) > 1 and loc[0] in ('body', 'query', 'path') else ''
        issues.append({'field': field, 'location': loc,
                       'message': messages.get(error['type'], 'Thông tin này chưa hợp lệ.'), 'hint': ''})
    return JSONResponse({'detail': jsonable_encoder(exc.errors()), 'issues': issues}, status_code=422)


# Services
revoland_service = RevolandService()
group_manager = GroupManager()
poster_engine = FacebookPosterEngine()
session_manager = FacebookSessionManager()
campaign_service = CampaignService(
    revoland_service=revoland_service,
    group_manager=group_manager,
    poster_engine=poster_engine
)
lead_service = LeadFilterService()
website_service = WebsiteSourceService()


STATIC_HTML_PATH = Path(__file__).resolve().parent / "static" / "index.html"


# --- Request DTOs ---
class ConfigUpdateRequest(BaseModel):
    revoland_api_url: Optional[str] = None
    revoland_api_key: Optional[str] = None
    revoland_mock_mode: Optional[bool] = None
    contact_phone: Optional[str] = None
    contact_name: Optional[str] = None
    min_delay_seconds: Optional[int] = None
    max_delay_seconds: Optional[int] = None
    max_groups_per_batch: Optional[int] = None
    headless_posting: Optional[bool] = None


class GroupCreateRequest(BaseModel):
    name: str
    group_url: str
    category: Optional[str] = "Chung"
    notes: Optional[str] = None


class GroupImportRequest(BaseModel):
    raw_text: str


class CampaignCreateRequest(BaseModel):
    listing_id: str
    target_group_ids: List[str]
    custom_content: Optional[str] = None
    preview_token: str


class ResolveTaskRequest(BaseModel):
    outcome: str
    post_url: Optional[str] = None
    confirmed: bool = False


def public_config(cfg):
    return {**{k: v for k, v in cfg.items() if k not in ('revoland_api_key', 'paraphrase_api_key', 'paraphrase_model', 'fb_profile_dir')},
            'api_key_configured': bool(cfg.get('revoland_api_key'))}


# --- Web UI Route ---
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return FileResponse(STATIC_HTML_PATH.parent / 'workflow.html')


@app.get('/leads', response_class=HTMLResponse)
def serve_lead_dashboard():
    return FileResponse(STATIC_HTML_PATH.parent / 'leads.html')


@app.get('/assets/workflow.js')
def serve_workflow_javascript():
    return FileResponse(STATIC_HTML_PATH.parent / 'workflow.js', media_type='application/javascript')


@app.get('/assets/common.js')
def serve_common_javascript():
    return FileResponse(STATIC_HTML_PATH.parent / 'common.js', media_type='application/javascript')


@app.get('/assets/source-example.json')
def download_source_example():
    return FileResponse(STATIC_HTML_PATH.parent / 'source-example.json', media_type='application/json', filename='source-example.json')


@app.get('/assets/posts-example.json')
def download_posts_example():
    return FileResponse(STATIC_HTML_PATH.parent / 'posts-example.json', media_type='application/json', filename='bai_dang_mau.json')


@app.get('/demo/real-estate', response_class=HTMLResponse)
def serve_demo_website():
    return demo_html()


class SourceImportRequest(BaseModel):
    url: str = Field(max_length=2048)


class JsonSourceRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: list | dict
    defer_images: bool = False
    compact: bool = False


@app.post('/api/sources/json')
def import_json_source(req: JsonSourceRequest):
    if not req.filename.lower().endswith('.json'):
        raise InputError('Hãy chọn file bài đăng có đuôi .json.', 'filename')
    rows = website_service.import_json(req.data, defer_images=req.defer_images)
    if req.compact:
        return [{**website_service.listing_summary(row), 'image_count': len(row.image_paths),
                 'pending_image_count': len(row.pending_image_urls), 'image_errors': row.image_errors}
                for row in rows]
    return [row.model_dump(exclude={'image_paths'}) for row in rows]


class CleanPostRequest(BaseModel):
    content: str


@app.post('/api/sources/clean-content')
def clean_source_content(req: CleanPostRequest):
    content = clean_post_html(req.content)
    return {'content': content, 'changed': content != req.content}


class ManualSourceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=50000)
    price_text: str = Field(default='', max_length=256)
    location: str = Field(default='', max_length=512)
    area_m2: Optional[float] = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)
    images_base64: list[str] = Field(default_factory=list, max_length=12)


class QuinLandImportRequest(BaseModel):
    record_ids: list[str] = Field(default_factory=list, max_length=15)
    max_images: int = Field(default=4, ge=1, le=12)


class WebsiteCampaignRequest(CampaignCreateRequest):
    min_delay_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    max_delay_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    image_indices: list[int] = Field(default_factory=list)
    reviewed: bool = False


@app.get('/api/sources/quinland')
def list_quinland_catalog(q: str = '', limit: int = 80):
    return website_service.list_quinland_catalog(query=q, limit=limit)


@app.post('/api/sources/quinland/import')
def import_quinland_source(req: QuinLandImportRequest):
    rows = website_service.import_quinland(record_ids=req.record_ids or None, max_images=req.max_images)
    return [row.model_dump(exclude={'image_paths'}) for row in rows]


@app.post('/api/sources/import')
def import_website_source(req: SourceImportRequest):
    try:
        rows = website_service.import_url(req.url)
    except InputError:
        raise
    except ValueError as exc:
        raise InputError(str(exc), 'source_url', hint='Kiểm tra lại đường dẫn và định dạng dữ liệu của nguồn tin.') from exc
    return [row.model_dump(exclude={'image_paths'}) for row in rows]


@app.post('/api/sources/manual')
def import_manual_source(req: ManualSourceRequest):
    rows = website_service.import_manual(
        title=req.title, description=req.description, price_text=req.price_text,
        location=req.location, area_m2=req.area_m2, images_base64=req.images_base64,
    )
    return [row.model_dump(exclude={'image_paths'}) for row in rows]


@app.post('/api/sources/demo')
def import_demo_source():
    return [row.model_dump(exclude={'image_paths'}) for row in website_service.import_demo()]


@app.get('/api/sources/listings')
def list_website_listings(summary: bool = False, q: str = '', offset: int = 0, limit: int = 100, selected_id: str = ''):
    if summary:
        return website_service.listing_catalog(q, offset, limit, selected_id)
    return [row.model_dump(exclude={'image_paths'}) for row in website_service.list_listings()]


class DeleteSourcesRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=10000)
    delete_all: bool = False


@app.post('/api/sources/listings/delete')
def delete_source_listings(req: DeleteSourcesRequest):
    if not req.delete_all and not req.ids:
        raise InputError('Hãy chọn bài cần xóa.', 'saved_ids')
    return {'deleted': website_service.delete_listings(req.ids, req.delete_all)}


@app.post('/api/sources/listings/{listing_id}/load-images')
def load_source_images(listing_id: str):
    if not website_service.load_listing_images(listing_id):
        raise InputError('Không tìm thấy tin nguồn.', 'listing_id', status_code=404, hint='Bài đã bị xóa hoặc thay đổi. Chọn lại bài từ kho đã lưu.')
    return preview_website_listing(listing_id)


@app.get('/api/sources/listings/{listing_id}/preview')
def preview_website_listing(listing_id: str):
    listing = website_service.get_listing_by_id(listing_id)
    if not listing:
        raise InputError('Không tìm thấy tin nguồn.', 'listing_id', status_code=404, hint='Bài đã bị xóa hoặc thay đổi. Chọn lại bài từ kho đã lưu.')
    provider = website_service.provider(listing, list(range(len(listing.media_urls))))
    return {'listing': {**listing.model_dump(exclude={'image_paths', 'pending_image_urls'}),
                        'pending_image_count': len(listing.pending_image_urls)},
            'formatted_text': provider.format_post_content(listing),
            'preview_token': hashlib.sha256(listing.model_dump_json().encode()).hexdigest(),
            'media_urls': [f'/api/sources/listings/{listing.id}/images/{i}' for i in range(len(listing.image_paths))]}


@app.get('/api/sources/listings/{listing_id}/images/{index}')
def serve_source_image(listing_id: str, index: int):
    listing = website_service.get_listing_by_id(listing_id)
    if not listing or not 0 <= index < len(listing.image_paths):
        raise HTTPException(status_code=404, detail='Không tìm thấy ảnh.')
    return FileResponse(listing.image_paths[index], media_type='image/jpeg')


@app.post('/api/workflow/campaigns')
def create_website_campaign(req: WebsiteCampaignRequest):
    if not req.reviewed:
        raise InputError('Cần kiểm tra nội dung, ảnh, tình trạng tin và quyền sử dụng trước khi tạo chiến dịch.', 'reviewed', hint='Đọc lại bài, sau đó đánh dấu ô xác nhận đã duyệt.')
    listing = website_service.get_listing_by_id(req.listing_id)
    if not listing:
        raise InputError('Không tìm thấy tin nguồn.', 'listing_id', hint='Chọn lại bài trong danh sách đã lưu.')
    if listing.pending_image_urls:
        raise InputError('Hãy tải ảnh của bài và duyệt lại trước khi chuẩn bị đăng.', 'image_indices', hint='Chọn lại bài để tải ảnh, rồi kiểm tra ảnh hiển thị.')
    if req.custom_content is not None and clean_post_html(req.custom_content) != req.custom_content:
        raise InputError('Nội dung còn mã HTML. Bấm Làm sạch mã HTML rồi kiểm tra và duyệt lại bài.', 'custom_content', hint='Làm sạch mã HTML và duyệt lại nội dung trước khi lưu đợt đăng.')
    provider = website_service.provider(listing, req.image_indices)
    campaign = campaign_service.create_campaign(req.listing_id, req.target_group_ids,
        req.custom_content, req.preview_token, listing_service=provider, expected_image_count=len(req.image_indices),
        min_delay_seconds=req.min_delay_seconds, max_delay_seconds=req.max_delay_seconds)
    return {'success': True, 'campaign': campaign.model_dump()}


class FeedbackRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)


def publication_target(campaign, task):
    return {'post_url': task.post_url, 'context': {
        'listing_id': campaign.listing_id, 'campaign_id': campaign.id,
        'posting_task_id': task.task_id, 'group_name': task.group_name,
        'listing_source_url': campaign.source_url}}


@app.post('/api/workflow/campaigns/{campaign_id}/comments')
def collect_campaign_comments(campaign_id: str, req: FeedbackRequest):
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign or campaign.source_mode != 'live':
        raise ValueError('Chọn một đợt đăng thật để lấy bình luận.')
    if campaign.status in ('queued', 'running'):
        raise ValueError('Đợi đăng bài hoàn tất rồi lấy bình luận.')
    targets = [publication_target(campaign, task) for task in campaign.tasks
               if task.status == GroupPostStatusEnum.POSTED and task.post_url and task.evidence]
    if not targets:
        raise ValueError('Chưa có bài xác nhận đăng thành công để lấy bình luận.')
    return lead_service.start_batch(targets, req.limit, context={
        'campaign_id': campaign.id, 'listing_id': campaign.listing_id,
        'group_name': 'Tất cả bài đã đăng', 'listing_source_url': campaign.source_url})


@app.post('/api/workflow/campaigns/{campaign_id}/tasks/{task_id}/comments')
def collect_publication_comments(campaign_id: str, task_id: str, req: FeedbackRequest):
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign:
        raise ValueError('Không tìm thấy chiến dịch.')
    task = next((task for task in campaign.tasks if task.task_id == task_id), None)
    if campaign.source_mode != 'live' or not task or task.status != GroupPostStatusEnum.POSTED or not task.post_url or not task.evidence:
        raise ValueError('Chỉ lấy bình luận từ bài đã xác nhận đăng và có permalink. Bài chờ duyệt/chưa rõ cần xác minh trước.')
    if campaign.status in ('queued', 'running'):
        raise ValueError('Đợi đăng bài hoàn tất rồi lấy bình luận.')
    target = publication_target(campaign, task)
    return lead_service.start(target['post_url'], req.limit, context=target['context'])


@app.get('/posting', response_class=HTMLResponse)
def serve_posting_dashboard():
    if STATIC_HTML_PATH.exists():
        return FileResponse(STATIC_HTML_PATH)
    return HTMLResponse("<h1>Revoland Facebook Poster Tool v2.0 is running</h1>")


@app.get('/assets/app.js')
def serve_javascript():
    return FileResponse(STATIC_HTML_PATH.parent / 'app.js', media_type='application/javascript')


@app.get('/assets/leads.js')
def serve_lead_javascript():
    return FileResponse(STATIC_HTML_PATH.parent / 'leads.js', media_type='application/javascript')


@app.get('/assets/leads.css')
def serve_lead_styles():
    return FileResponse(STATIC_HTML_PATH.parent / 'leads.css', media_type='text/css')


class CollectionRequest(BaseModel):
    post_url: str
    limit: int = 100


@app.get('/api/leads/registries')
def get_lead_registries():
    return registry_inventory()


@app.post('/api/leads/filter')
def filter_imported_comments(payload: Any = Body(...)):
    result = filter_records(payload)
    from services.customer_records import aggregate_customers
    return summarize_records(aggregate_customers(result['records']))


@app.post('/api/leads/collect')
def collect_facebook_comments(req: CollectionRequest):
    return lead_service.start(req.post_url, req.limit)


@app.get('/api/leads/runs')
def list_lead_runs():
    return lead_service.list_runs()


@app.get('/api/leads/results')
def get_customer_results(campaign_id: Optional[str] = None, group_key: Optional[str] = None,
                         classification: Optional[str] = None, q: str = '', posting_task_id: Optional[str] = None, interest_level: Optional[str] = None):
    result = lead_service.customer_results()
    saved_campaigns = campaign_service.list_campaigns()
    titles = {c.id: c.listing_title for c in saved_campaigns}
    dates = {c.id: c.created_at for c in saved_campaigns}
    campaigns, groups = dict(titles), {}
    for row in result['records']:
        for source in row.get('sources') or [row]:
            cid = source.get('campaign_id') or '__external__'
            source['campaign_title'] = titles.get(cid, 'Bài ngoài đợt đăng' if cid == '__external__' else cid)
            campaigns[cid] = source['campaign_title']
            groups[source['group_key']] = source.get('group_name') or (
                'Bài ngoài nhóm' if source['group_key'] == '__external__' else source['group_key'])
        row['campaign_title'] = titles.get(row.get('campaign_id'), row.get('campaign_id') or 'Bài ngoài đợt đăng')
    filtered = select_customer_records(result['records'], campaign_id, group_key, classification, q, posting_task_id, interest_level)
    return {**result, **summarize_records(filtered),
            'campaigns': [{'id': cid, 'title': title, 'created_at': dates.get(cid)} for cid, title in campaigns.items()],
            'groups': [{'key': key, 'name': name} for key, name in groups.items()]}


@app.get('/api/leads/results/excel')
def export_customer_results(campaign_id: Optional[str] = None, group_key: Optional[str] = None,
                            classification: Optional[str] = None, q: str = '', posting_task_id: Optional[str] = None, interest_level: Optional[str] = None):
    records = select_customer_records(lead_service.customer_results()['records'], campaign_id, group_key,
                                       classification, q, posting_task_id, interest_level)
    return excel_response(workbook_bytes(export_records_to_excel, records), 'facebook_leads.xlsx')


@app.get('/api/leads/runs/{run_id}')
def get_lead_run(run_id: str):
    return lead_service.get_for_display(run_id)


@app.post('/api/leads/runs/{run_id}/stop')
def stop_lead_collection(run_id: str):
    return lead_service.stop(run_id)


@app.get('/api/leads/runs/{run_id}/excel')
def export_lead_run(run_id: str, classification: Optional[str] = None, campaign_id: Optional[str] = None,
                    group_key: Optional[str] = None, q: str = '', posting_task_id: Optional[str] = None, interest_level: Optional[str] = None):
    if classification not in (None, 'LEAD_POTENTIAL', 'NEEDS_REVIEW', 'IGNORE'):
        raise ValueError('Phân loại không hợp lệ.')
    records = lead_service.get_for_display(run_id)['records']
    records = select_customer_records(records, campaign_id, group_key, classification, q, posting_task_id, interest_level)
    return excel_response(workbook_bytes(export_records_to_excel, records), 'facebook_leads.xlsx')


# --- 1. Revoland API Endpoints ---
@app.get("/api/config")
def get_system_config():
    return public_config(load_config())


@app.post("/api/config")
def update_system_config(req: ConfigUpdateRequest):
    if campaign_service.busy:
        raise ResourceBusyError('Đợi chiến dịch hoàn tất trước khi đổi cấu hình.')
    data = req.model_dump(exclude_unset=True, exclude_none=True)
    if not data.get('revoland_api_key', '').strip():
        data.pop('revoland_api_key', None)
    cfg = load_config()
    cfg.update(data)
    from urllib.parse import urlsplit
    url = urlsplit(cfg['revoland_api_url'])
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('API URL phải là địa chỉ HTTP(S) không chứa mật khẩu, query hoặc fragment.')
    if not 0 <= cfg['min_delay_seconds'] <= cfg['max_delay_seconds'] <= 3600:
        raise ValueError('Khoảng nghỉ cần thỏa 0 ≤ tối thiểu ≤ tối đa ≤ 3600 giây.')
    if not 1 <= int(cfg.get('max_groups_per_batch', 100)) <= 100:
        raise ValueError('Số nhóm tối đa mỗi đợt phải từ 1 đến 100 nhóm.')
    cfg['max_groups_per_batch'] = int(cfg.get('max_groups_per_batch', 100))
    save_config(cfg)
    revoland_service.config = cfg
    poster_engine.config = cfg
    campaign_service.config = cfg
    return {"success": True, "message": "Đã lưu cấu hình hệ thống thành công", "config": public_config(cfg)}


@app.post("/api/revoland/test-connection")
def test_revoland_connection():
    return revoland_service.test_connection()


@app.get("/api/revoland/listings")
def get_revoland_listings():
    listings = revoland_service.get_listings()
    return [item.model_dump() for item in listings]


@app.get("/api/revoland/listings/{listing_id}")
def get_revoland_listing_detail(listing_id: str):
    item = revoland_service.get_listing_by_id(listing_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy căn hộ")
    return item.model_dump()


@app.get("/api/revoland/listings/{listing_id}/preview")
def preview_listing_post(listing_id: str):
    item = revoland_service.get_listing_by_id(listing_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy căn hộ")
    formatted_text = revoland_service.format_post_content(item)
    return {
        "listing": item.model_dump(),
        "formatted_text": formatted_text,
        "media_urls": item.media_urls,
        "preview_token": hashlib.sha256(item.model_dump_json().encode()).hexdigest(),
    }


# --- 2. Facebook Session Endpoints ---
@app.get("/api/session/status")
def get_session_status(quick: bool = False):
    """quick=true trả trạng thái đã biết mà không mở Chromium (dùng cho huy hiệu trên giao diện)."""
    status = session_manager.quick_status() if quick else session_manager.check_session_status()
    return status.model_dump()


@app.post("/api/session/login")
def open_fb_login():
    """Mở trình duyệt thực tế để khách tự đăng nhập Facebook (có 2FA) và lưu phiên."""
    if campaign_service.busy:
        raise ResourceBusyError('Đợi chiến dịch hoàn tất trước khi đăng nhập.')
    session_manager.start_login(180)
    return {
        "success": True,
        "message": "Đang mở cửa sổ trình duyệt đăng nhập Facebook trên màn hình. Khách hãy nhập mật khẩu và mã xác thực OTP (2FA) để lưu phiên."
    }


@app.post("/api/session/logout")
def clear_fb_session():
    """Xóa sạch phiên Facebook và cookies trên máy."""
    if campaign_service.busy:
        raise ResourceBusyError('Đợi chiến dịch hoàn tất trước khi xóa phiên.')
    return session_manager.logout_and_clear_session()


# --- 3. Facebook Groups Endpoints ---
@app.get("/api/groups")
def get_groups():
    groups = group_manager.list_groups()
    return [g.model_dump() for g in groups]


@app.post("/api/groups")
def add_group(req: GroupCreateRequest):
    g = group_manager.add_group(
        name=req.name,
        group_url=req.group_url,
        category=req.category,
        notes=req.notes
    )
    return {"success": True, "group": g.model_dump()}


@app.delete("/api/groups/{group_id}")
def delete_group(group_id: str):
    success = group_manager.delete_group(group_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhóm để xóa")
    return {"success": True, "message": "Đã xóa nhóm khỏi danh sách"}


@app.post("/api/groups/import")
def import_groups(req: GroupImportRequest):
    count = group_manager.import_groups_from_text(req.raw_text)
    return {
        "success": True,
        "imported_count": count,
        "message": f"Đã nhận diện và thêm {count} nhóm Facebook mới vào danh sách."
    }


# --- 4. Posting Campaign Endpoints ---
@app.post("/api/campaigns/create")
def create_posting_campaign(req: CampaignCreateRequest):
    try:
        camp = campaign_service.create_campaign(
            listing_id=req.listing_id,
            target_group_ids=req.target_group_ids,
            custom_content=req.custom_content,
            preview_token=req.preview_token,
        )
        return {"success": True, "campaign": camp.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/campaigns/{campaign_id}/execute")
def execute_posting_campaign(campaign_id: str):
    if not campaign_service.get_campaign(campaign_id):
        raise InputError('Không tìm thấy chiến dịch.', 'campaign_id', status_code=404)
    if session_manager._login_lock.locked():
        raise InputError('Hãy hoàn tất đăng nhập trước khi đăng bài.', 'facebook_session', status_code=409, hint='Hoàn tất đăng nhập trong cửa sổ Facebook đang mở rồi thử lại.')
    # Validation/trạng thái không hợp lệ trả 400 qua handler ValueError chung.
    camp = campaign_service.start_campaign(campaign_id)
    return {"success": True, "campaign": camp.model_dump()}


@app.post("/api/campaigns/{campaign_id}/retry")
def retry_failed_campaign_tasks(campaign_id: str):
    if not campaign_service.get_campaign(campaign_id):
        raise InputError('Không tìm thấy chiến dịch.', 'campaign_id', status_code=404)
    if session_manager._login_lock.locked():
        raise InputError('Hãy hoàn tất đăng nhập trước khi thử lại.', 'facebook_session', status_code=409)
    camp = campaign_service.start_campaign(campaign_id, retry=True)
    return {"success": True, "campaign": camp.model_dump()}


@app.get("/api/campaigns")
def list_campaigns():
    campaigns = campaign_service.list_campaigns()
    return [c.model_dump() for c in campaigns]


@app.get("/api/campaigns/{campaign_id}")
def get_campaign_detail(campaign_id: str):
    camp = campaign_service.get_campaign(campaign_id)
    if not camp:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    return camp.model_dump()


class AutoCheckRequest(BaseModel):
    task_id: Optional[str] = None
    continue_pending: bool = False


@app.post("/api/campaigns/{campaign_id}/auto-check")
def auto_check_campaign_tasks(campaign_id: str, req: AutoCheckRequest = Body(default=AutoCheckRequest())):
    if not campaign_service.get_campaign(campaign_id):
        raise InputError('Không tìm thấy chiến dịch.', 'campaign_id', status_code=404)
    if session_manager._login_lock.locked():
        raise ResourceBusyError('Hãy hoàn tất đăng nhập trước khi kiểm tra.')
    camp = campaign_service.start_auto_verify(
        campaign_id, task_id=req.task_id, continue_pending=req.continue_pending
    )
    return {"success": True, "campaign": camp.model_dump()}


@app.post('/api/campaigns/{campaign_id}/tasks/{task_id}/resolve')
def resolve_task(campaign_id: str, task_id: str, req: ResolveTaskRequest):
    if not req.confirmed:
        raise ValueError('Khách cần kiểm tra nhóm Facebook và xác nhận kết quả trước.')
    camp = campaign_service.resolve_task(campaign_id, task_id, req.outcome, req.post_url)
    return {'success': True, 'campaign': camp.model_dump()}


def excel_response(content, filename):
    return StreamingResponse(BytesIO(content),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get('/api/exports/campaigns')
def export_campaign_results(campaign_id: Optional[str] = None):
    if campaign_id is not None and not campaign_service.get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail='Không tìm thấy chiến dịch để xuất.')
    return excel_response(campaign_report_bytes(campaign_service, campaign_id), 'ket_qua_dang_bai.xlsx')


@app.get('/api/exports/comments/example')
def download_comment_example():
    return JSONResponse(COMMENT_EXAMPLE,
        headers={'Content-Disposition':'attachment; filename="binh_luan_mau.json"'})


@app.post('/api/exports/comments')
def export_comment_results(payload: Any = Body(...)):
    return excel_response(comment_report_bytes(payload), 'binh_luan_lead.xlsx')


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=False, workers=1)
