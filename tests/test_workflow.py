"""Website → approved Facebook campaign → linked comment leads, entirely offline."""
from io import BytesIO
import json
from pathlib import Path
import socket
from unittest.mock import Mock

from fastapi.testclient import TestClient
from PIL import Image
import openpyxl
import pytest
from playwright.sync_api import sync_playwright

from api import server
from models.schema import GroupTaskResult, GroupPostStatusEnum as S
from services.campaign_service import CampaignService
from services.group_manager import GroupManager
from services.lead_filter_service import LeadFilterService
from services import website_source as source


SOURCE_URL = 'https://properties.example/listing/1'
PROPERTY = {'source_url': SOURCE_URL, 'title': 'Căn kiểm thử <img src=x onerror="window.injected=1">',
    'description': 'Thông tin bất động sản từ nguồn kiểm thử.', 'price_text': '2 tỷ',
    'location': 'Khu vực kiểm thử', 'media_urls': ['https://properties.example/photo.png']}


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(source.socket, 'getaddrinfo', lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 443))])


@pytest.mark.parametrize('value', ['file:///secret', 'https://user:pw@host.test/a',
    'http://host.test:9000/a', 'https://localhost/a'])
def test_source_rejects_private_or_invalid_urls(value, monkeypatch):
    monkeypatch.setattr(source.socket, 'getaddrinfo', lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80))])
    with pytest.raises(ValueError): source.public_url(value)


def test_source_checks_each_redirect_and_download_bound(public_dns, monkeypatch):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.status_code = 302
    response.headers = {'Location': 'http://private.test/a'}
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.get.return_value = response
    monkeypatch.setattr(source.requests, 'Session', lambda: session)
    public = source.public_url
    def guarded(url):
        if 'private.test' in url: raise ValueError('private redirect')
        return public(url)
    monkeypatch.setattr(source, 'public_url', guarded)
    with pytest.raises(ValueError, match='private redirect'): source.fetch_public(SOURCE_URL, 5)
    response.status_code = 200
    response.headers = {'Content-Type': 'text/html'}
    response.iter_content.return_value = [b'123456']
    with pytest.raises(ValueError, match='dung lượng'): source.fetch_public(SOURCE_URL, 5)


def test_structured_html_missing_fields_units_and_unrelated_nodes():
    payload = {'@graph': [
        {'@type': 'Article', 'name': 'Unrelated', 'description': 'Not a property'},
        {'@type': 'RealEstateListing', 'name': 'Căn hộ', 'description': '<p>Mô tả <b>chi tiết</b></p>',
         'url': '/listing/2', 'offers': {'price': 100, 'priceCurrency': 'VND', 'availability': 'https://schema.org/SoldOut',
            'itemOffered': {'@type': 'Apartment', 'floorSize': {'value': 600, 'unitCode': 'FTK'}}}}]}
    rows = source.structured_properties('<script type="application/ld+json">'+json.dumps(payload)+'</script>', SOURCE_URL)
    assert len(rows) == 1 and rows[0]['status'] == 'sold'
    assert rows[0]['area_m2'] is None and rows[0]['location'].startswith('Chưa có')
    assert rows[0]['description'] == 'Mô tả chi tiết'
    assert rows[0]['source_url'] == 'https://properties.example/listing/2'


@pytest.fixture
def source_service(tmp_path, monkeypatch, public_dns):
    image = BytesIO()
    Image.new('RGB', (10, 8), 'green').save(image, 'PNG')
    def fetch(url, limit):
        if url.endswith(('photo.png', '.jpg', '.jpeg')): return image.getvalue(), url, 'image/png'
        return json.dumps({'listings': [PROPERTY]}).encode(), url, 'application/json'
    monkeypatch.setattr(source, 'fetch_public', fetch)
    return source.WebsiteSourceService(tmp_path / 'sources')


def test_image_snapshot_selection_integrity_and_source_persistence(source_service):
    listing = source_service.import_url(SOURCE_URL)[0]
    assert listing.source_mode == 'live' and listing.bedrooms is None and listing.area_m2 is None
    assert Image.open(listing.image_paths[0]).format == 'JPEG'
    assert source_service.provider(listing, []).download_listing_images(listing) == []
    assert len(source_service.provider(listing, [0]).download_listing_images(listing)) == 1
    with pytest.raises(ValueError): source_service.provider(listing, [0, 0])
    with pytest.raises(ValueError): source_service.provider(listing, [-1])
    restored = source.WebsiteSourceService(source_service.root).get_listing_by_id(listing.id)
    assert restored.image_hashes == listing.image_hashes
    Path(listing.image_paths[0]).write_bytes(b'changed')
    with pytest.raises(ValueError, match='snapshot'): source_service.provider(restored, [0]).download_listing_images(restored)


def test_demo_is_explicit_and_does_not_need_external_http(source_service):
    rows = source_service.import_demo()
    assert len(rows) == 2 and all(row.source_mode == 'mock' for row in rows)
    assert rows[0].image_paths and rows[0].image_hashes


def test_manual_listing_with_local_photos_posts_through_workflow(workflow):
    import base64
    client, campaigns, leads, group, engine = workflow
    buf = BytesIO()
    Image.new('RGB', (32, 24), 'navy').save(buf, 'PNG')
    data_url = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    res = client.post('/api/sources/manual', json={
        'title': 'Nhà phố chính chủ Quận 7',
        'price_text': '6,5 tỷ',
        'location': 'Quận 7, TP.HCM',
        'area_m2': 80,
        'description': 'Hẻm xe hơi, liên hệ 0912345678.',
        'images_base64': [data_url],
    })
    assert res.status_code == 200
    listing_id = res.json()[0]['id']
    preview = client.get(f'/api/sources/listings/{listing_id}/preview').json()
    assert 'Nguồn:' not in preview['formatted_text']
    assert '6,5 tỷ' in preview['formatted_text'] and '80 m²' in preview['formatted_text']
    assert client.get(preview['media_urls'][0]).status_code == 200
    created = client.post('/api/workflow/campaigns', json=create_payload(client, listing_id, group.id)).json()['campaign']
    posted = campaigns.execute_campaign(created['id'])
    assert posted.tasks[0].status == S.POSTED
    assert engine.post_to_single_group.call_count == 1
    assert client.post('/api/sources/manual', json={'title': 'A', 'description': 'B', 'images_base64': ['not-base64']}).status_code == 400


def test_bad_source_is_rejected_without_mock_fallback(source_service, monkeypatch):
    monkeypatch.setattr(source, 'fetch_public', lambda url, limit: (b'<h1>Not a property source</h1>', url, 'text/html'))
    with pytest.raises(ValueError, match='Không nhận diện'): source_service.import_url(SOURCE_URL)
    assert source_service.list_listings() == []


@pytest.mark.parametrize('change', [{'source_url': ['invalid']}, {'media_urls': None}, {'media_urls': [123]}])
def test_malformed_api_fields_have_clear_validation(source_service, monkeypatch, change):
    monkeypatch.setattr(source, 'fetch_public', lambda url, limit: (json.dumps([{**PROPERTY, **change}]).encode(), url, 'application/json'))
    with pytest.raises(ValueError, match='Mỗi tin'): source_service.import_url(SOURCE_URL)


def test_malformed_jsonld_metadata_is_not_fabricated():
    payload = [{'@type': [{}]}, {'@type': 'RealEstateListing', 'name': 'Tin', 'description': 'Mô tả',
               'url': {'unexpected': 'object'}, 'offers': {'price': {'@id': 'price1'}}}]
    rows = source.structured_properties('<script type="application/ld+json">'+json.dumps(payload)+'</script>', SOURCE_URL)
    assert len(rows) == 1 and rows[0]['source_url'] == SOURCE_URL
    assert rows[0]['price_text'] == 'Chưa có thông tin giá'


def test_multi_record_api_requires_distinct_source_urls(source_service, monkeypatch):
    row = {**PROPERTY, 'media_urls': []}
    monkeypatch.setattr(source, 'fetch_public', lambda url, limit: (json.dumps([row, row]).encode(), url, 'application/json'))
    with pytest.raises(ValueError, match='source_url riêng'): source_service.import_url(SOURCE_URL)
    assert source_service.list_listings() == []


@pytest.fixture
def workflow(source_service, tmp_path, monkeypatch):
    groups = GroupManager(tmp_path / 'groups.json')
    group = groups.add_group('Nhóm kiểm thử', 'https://www.facebook.com/groups/fixture')
    engine = Mock()
    def submit(**kw):
        kw['before_submit']()
        return GroupTaskResult(task_id=kw['task_id'], group_id=group.id, group_name=group.name,
            group_url=group.group_url, status=S.POSTED, post_url=group.group_url+'/posts/123',
            evidence='offline-fixture', submission_started=True)
    engine.post_to_single_group.side_effect = submit
    campaigns = CampaignService(group_manager=groups, poster_engine=engine, db_path=tmp_path/'campaigns.sqlite3')
    campaigns.config.update(min_delay_seconds=0, max_delay_seconds=0)
    class Comments:
        def collect(self, url, limit, stop, progress):
            rows = [{'id': 'c1', 'fb_user_name': 'Khách mẫu', 'raw_content': 'Cần mua 0912345678', 'source_url': url,
                     'comment_url': url+'?comment_id=c1'},
                    {'id': 'c2', 'fb_user_name': 'Khách B', 'raw_content': 'xin giá', 'source_url': url},
                    {'id': 'c3', 'fb_user_name': 'Khách C', 'raw_content': 'không mua', 'source_url': url}][:limit]
            progress(rows)
            return 'partial', rows, 'Offline fixture: chưa xác nhận lấy đủ.'
    leads = LeadFilterService(tmp_path/'leads', tmp_path/'profile', Comments())
    monkeypatch.setattr(server, 'website_service', source_service)
    monkeypatch.setattr(server, 'campaign_service', campaigns)
    monkeypatch.setattr(server, 'group_manager', groups)
    monkeypatch.setattr(server, 'lead_service', leads)
    client = TestClient(server.app, base_url='http://localhost:8000', headers={'X-Revoland-Client': 'local'})
    return client, campaigns, leads, group, engine


def create_payload(client, listing_id, group_id):
    preview = client.get(f'/api/sources/listings/{listing_id}/preview').json()
    return {'listing_id': listing_id, 'target_group_ids': [group_id], 'custom_content': 'Nội dung đã kiểm tra',
        'preview_token': preview['preview_token'], 'image_indices': [0] if preview['media_urls'] else [], 'reviewed': True}


def test_json_posts_keep_content_and_images_through_posting(workflow):
    client, campaigns, leads, group, engine = workflow
    content = 'Bán căn hộ A\nGiá 2,85 tỷ, chưa gồm phí. Đang làm sổ.\nLiên hệ 0900000000'
    imported = client.post('/api/sources/json', json={'filename': 'posts.json', 'data': {'posts': [
        {'title': 'Căn hộ A', 'content': content, 'images': PROPERTY['media_urls']}]}})
    assert imported.status_code == 200, imported.text
    listing_id = imported.json()[0]['id']
    preview = client.get(f'/api/sources/listings/{listing_id}/preview').json()
    assert preview['formatted_text'] == content and len(preview['media_urls']) == 1
    payload = create_payload(client, listing_id, group.id)
    payload['custom_content'] = content
    created = client.post('/api/workflow/campaigns', json=payload)
    assert created.status_code == 200, created.text
    campaign = campaigns.get_campaign(created.json()['campaign']['id'])
    assert campaign.formatted_content == content and len(campaign.media_urls) == 1
    posted = campaigns.execute_campaign(campaign.id)
    assert posted.tasks[0].status == S.POSTED and engine.post_to_single_group.call_count == 1
    assert leads.list_runs() == []












def test_workflow_requires_approval_and_matching_preview_and_blocks_demo(workflow):
    client, campaigns, leads, group, engine = workflow
    demo_id = client.post('/api/sources/demo').json()[0]['id']
    payload = create_payload(client, demo_id, group.id)
    assert client.post('/api/workflow/campaigns', json={**payload, 'reviewed': False}).status_code == 400
    assert client.post('/api/workflow/campaigns', json={**payload, 'preview_token': 'stale'}).status_code == 400
    result = client.post('/api/workflow/campaigns', json=payload)
    assert result.status_code == 200
    campaign = result.json()['campaign']
    assert client.post(f'/api/campaigns/{campaign["id"]}/execute').status_code != 200
    assert engine.post_to_single_group.call_count == 0


def test_linked_collection_rejects_pending_unknown_and_exports_context(workflow):
    client, campaigns, leads, group, engine = workflow
    listing_id = client.post('/api/sources/import', json={'url': SOURCE_URL}).json()[0]['id']
    created = client.post('/api/workflow/campaigns', json=create_payload(client, listing_id, group.id)).json()['campaign']
    base = f'/api/workflow/campaigns/{created["id"]}/tasks/{created["tasks"][0]["task_id"]}/comments'
    assert client.post(base, json={'limit': 100}).status_code == 400
    posted = campaigns.execute_campaign(created['id'])
    assert posted.tasks[0].status == S.POSTED
    run = client.post(base, json={'limit': 100}).json()
    leads._thread.join(5)
    saved = leads.get(run['id'])
    assert saved['summary'] == {'total': 3, 'LEAD_POTENTIAL': 1, 'NEEDS_REVIEW': 1, 'IGNORE': 1}
    assert saved['context']['campaign_id'] == created['id']
    ws = openpyxl.load_workbook(BytesIO(client.get(f'/api/leads/runs/{run["id"]}/excel').content)).active
    assert ws['O2'].value == listing_id and ws['S2'].value == created['id']
    assert ws['U2'].value == group.name and ws['V2'].value == SOURCE_URL
    assert ws['W2'].value.endswith('comment_id=c1')
    for status in (S.UNKNOWN, S.PENDING_APPROVAL):
        posted.tasks[0].status = status
        campaigns._save(posted)
        assert client.post(base, json={'limit': 100}).status_code == 400


def test_manual_campaign_collection_only_reads_confirmed_posts_and_merges_refresh(workflow):
    client, campaigns, leads, group, engine = workflow
    listing_id = client.post('/api/sources/import', json={'url': SOURCE_URL}).json()[0]['id']
    created = client.post('/api/workflow/campaigns', json=create_payload(client, listing_id, group.id)).json()['campaign']
    endpoint = f'/api/workflow/campaigns/{created["id"]}/comments'
    assert client.post(endpoint, json={'limit': 100}).status_code == 400
    posted = campaigns.execute_campaign(created['id'])
    assert leads.list_runs() == []  # Posting never starts comment collection.
    first = posted.tasks[0]
    posted.tasks.extend([
        first.model_copy(update={'task_id': 'second', 'group_name': 'Nhóm hai',
                                 'post_url': 'https://www.facebook.com/groups/second/posts/456'}),
        first.model_copy(update={'task_id': 'pending', 'status': S.PENDING_APPROVAL}),
        first.model_copy(update={'task_id': 'unknown', 'status': S.UNKNOWN}),
    ])
    posted.total_groups = 4
    campaigns._save(posted)
    for _ in range(2):
        response = client.post(endpoint, json={'limit': 100})
        assert response.status_code == 200
        run = response.json()
        leads._thread.join(5)
        saved = leads.get(run['id'])
        assert saved['summary']['total'] == 6
        assert len(saved['targets']) == 2
        assert {r['posting_task_id'] for r in saved['records']} == {first.task_id, 'second'}
    wb = openpyxl.load_workbook(BytesIO(client.get(
        f'/api/leads/runs/{run["id"]}/excel?classification=LEAD_POTENTIAL').content))
    assert len(wb.worksheets) == 1
    assert wb.active.max_row == 3
    assert {wb.active['U2'].value, wb.active['U3'].value} == {group.name, 'Nhóm hai'}
    posted.status = 'running'
    campaigns._save(posted)
    assert client.post(endpoint, json={'limit': 100}).status_code == 400


def test_quinland_catalog_and_live_import_allows_campaign_execution(workflow):
    client, campaigns, leads, group, engine = workflow
    catalog = client.get('/api/sources/quinland?q=Vinhomes&limit=20').json()
    assert len(catalog) >= 1 and catalog[0]['price_text']
    imported = client.post('/api/sources/quinland/import', json={'record_ids': ['0', '4'], 'max_images': 2}).json()
    assert len(imported) == 2
    assert all(row['source_mode'] == 'live' for row in imported)
    assert '0935 482 682' not in imported[0]['description']
    assert imported[1]['price_text'] == '4,7 tỷ'
    preview = client.get(f"/api/sources/listings/{imported[0]['id']}/preview").json()
    assert len(preview['media_urls']) == 2 and '🏡' in preview['formatted_text']
    created = client.post('/api/workflow/campaigns', json={
        'listing_id': imported[0]['id'],
        'target_group_ids': [group.id],
        'custom_content': preview['formatted_text'],
        'preview_token': preview['preview_token'],
        'image_indices': [0, 1],
        'reviewed': True,
    })
    assert created.status_code == 200
    campaign_id = created.json()['campaign']['id']
    posted = campaigns.execute_campaign(campaign_id)
    assert posted.tasks[0].status == S.POSTED
    assert engine.post_to_single_group.call_count == 1


@pytest.mark.browser
def test_complete_browser_website_to_facebook_to_lead_excel(workflow):
    client, campaigns, leads, group, engine = workflow
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        errors, failures = [], []
        def serve(route):
            req = route.request
            assert req.url.startswith('http://localhost:8000/'), req.url
            response = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
            if response.status_code >= 400: failures.append((req.url, response.status_code))
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
        context.route('**/*', serve)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://localhost:8000/')
        page.locator('#other-sources').evaluate('(e) => e.open = true')
        page.locator('#source-url').fill(SOURCE_URL)
        page.locator('#import').click()
        page.wait_for_function("document.getElementById('content').value.includes('Thông tin bất động sản')")
        assert page.locator('.photo-choice').count() == 1
        assert page.evaluate('window.injected') is None
        approved = 'Nội dung đã duyệt đầy đủ 🏡\n' + 'Thông tin chi tiết. ' * 20
        page.locator('#content').fill(approved)
        page.locator('.group-choice').check()
        page.locator('#min-delay').fill('42')
        page.locator('#max-delay').fill('42')
        assert 'Thời gian nghỉ càng ngắn' in page.locator('#step-3').inner_text()
        page.locator('#reviewed').check()
        page.locator('#create').click()
        page.wait_for_function("!document.getElementById('execute').disabled")
        screenshot = Path(__file__).resolve().parents[1]/'.cache' / 'test-runs'/'facebook-workflow.png'
        page.screenshot(path=str(screenshot), full_page=True)
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#execute').click()
        page.wait_for_function("document.getElementById('tasks').innerText.includes('Đã xác nhận đăng')")
        saved = campaigns.list_campaigns()[0]
        assert saved.min_delay_seconds == saved.max_delay_seconds == 42
        assert saved.formatted_content == approved and len(saved.media_urls) == 1
        assert engine.post_to_single_group.call_count == 1
        assert leads.list_runs() == []
        assert page.locator('#collect-all').count() == 0
        assert page.get_by_role('link', name='Mở bài đã đăng ↗').get_attribute('href') == saved.tasks[0].post_url
        assert page.get_by_role('link', name='Lọc comment tại tab Khách hàng →').count() == 1
        engine.check_saved_post.return_value = {'status': 'unavailable', 'message': 'Link không còn hiển thị'}
        page.get_by_role('button', name='Kiểm tra link bài này').click()
        page.wait_for_function("document.getElementById('tasks').innerText.includes('Đã đăng · hiện không hiển thị')")
        assert engine.check_saved_post.call_args.args[0] == saved.tasks[0].post_url
        assert engine.post_to_single_group.call_count == 1
        page.get_by_role('link', name='Lọc comment tại tab Khách hàng →').click()
        page.wait_for_function("!document.getElementById('collect-selected').disabled")
        assert page.locator('#collection-campaign').input_value() == saved.id
        assert page.locator('#collection-task').input_value() == saved.tasks[0].task_id
        page.locator('#collect-selected').click()
        page.wait_for_function("document.getElementById('total').innerText === '3'")
        assert group.name in page.locator('#results').inner_text()
        page.locator('#classification').select_option('LEAD_POTENTIAL')
        with page.expect_download() as download:
            page.locator('#export').click()
        ws = openpyxl.load_workbook(BytesIO(download.value.path().read_bytes())).active
        assert ws.max_row == 2 and ws['E2'].value == '0912345678'
        assert ws['S2'].value == saved.id and ws['V2'].value == SOURCE_URL
        leads._thread.join(5)
        page.locator('#collection-task').select_option('')
        for _ in range(2):
            page.wait_for_function("!document.getElementById('collect-selected').disabled")
            page.locator('#collect-selected').click()
            page.wait_for_function("!document.getElementById('collect-selected').disabled")
            leads._thread.join(5)
        assert page.locator('#total').inner_text() == '3'
        page.locator('#classification').select_option('LEAD_POTENTIAL')
        assert page.locator('#results tr').count() == 1
        page.screenshot(path=str(screenshot.with_name('customer-hub.png')), full_page=True)
        assert not failures and not errors
        context.close()
        browser.close()


def test_deleting_source_keeps_prepared_campaign_usable(workflow):
    client, campaigns, _, group, engine = workflow
    imported = client.post('/api/sources/json', json={'filename': 'fast.json', 'data': [
        {'content': 'Bài nạp nhanh', 'images': PROPERTY['media_urls']}], 'defer_images': True}).json()[0]
    listing_id = imported['id']
    blocked = client.post('/api/workflow/campaigns', json=create_payload(client, listing_id, group.id))
    assert blocked.status_code == 400 and 'tải ảnh' in blocked.json()['detail']
    assert client.post(f'/api/sources/listings/{listing_id}/load-images').status_code == 200
    response = client.post('/api/workflow/campaigns', json=create_payload(client, listing_id, group.id))
    assert response.status_code == 200
    campaign_id = response.json()['campaign']['id']
    images = campaigns.get_campaign(campaign_id).media_urls
    assert images and all(Path(path).is_file() for path in images)
    assert client.post('/api/sources/listings/delete', json={'ids': [listing_id]}).json()['deleted'] == 1
    assert client.get(f'/api/sources/listings/{listing_id}/preview').status_code == 404
    posted = campaigns.execute_campaign(campaign_id)
    assert posted.tasks[0].status == S.POSTED
    engine.post_to_single_group.assert_called_once()
