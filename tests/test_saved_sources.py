from io import BytesIO
from pathlib import Path
import json

from fastapi.testclient import TestClient
from PIL import Image
from playwright.sync_api import sync_playwright
import pytest

from api import server
from services import website_source as source


@pytest.fixture
def saved_source(tmp_path, monkeypatch):
    service = source.WebsiteSourceService(tmp_path / 'sources')
    monkeypatch.setattr(server, 'website_service', service)
    data = BytesIO()
    Image.new('RGB', (24, 16), 'green').save(data, 'PNG')
    fetched = []
    def fetch(url, limit=None, referer=None):
        fetched.append(url)
        return data.getvalue(), url, 'image/png'
    monkeypatch.setattr(source, 'fetch_public', fetch)
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    return service, client, fetched


def posts(count):
    return [{'title': f'Căn hộ {i:03}', 'content': f'Nội dung {i}',
             'images': [f'https://photos.example/{i}.jpg']} for i in range(count)]


def test_fast_import_loads_only_selected_images_and_reuses_them(saved_source):
    service, client, fetched = saved_source
    payload = posts(3)
    imported = client.post('/api/sources/json', json={'filename': 'x.json', 'data': payload,
        'defer_images': True, 'compact': True}).json()
    assert len(imported) == 3 and fetched == []
    assert imported[0]['pending_image_count'] == 1 and 'content' not in imported[0]
    listing_id = imported[0]['id']
    assert client.get(f'/api/sources/listings/{listing_id}/preview').json()['listing']['pending_image_count'] == 1
    response = client.post(f'/api/sources/listings/{listing_id}/load-images').json()
    assert response['listing']['pending_image_count'] == 0
    assert fetched == [payload[0]['images'][0]]
    assert client.get(response['media_urls'][0]).status_code == 200
    token = response['preview_token']
    assert client.post(f'/api/sources/listings/{listing_id}/load-images').json()['preview_token'] == token
    service.import_json(payload, defer_images=True)
    assert service.get_listing_by_id(listing_id).image_paths
    assert fetched == [payload[0]['images'][0]]
    assert len(service.get_listing_by_id(imported[1]['id']).pending_image_urls) == 1


def test_catalog_is_paged_searchable_and_omits_post_bodies(saved_source):
    service, client, _ = saved_source
    rows = service.import_json(posts(205), defer_images=True)
    response = client.get('/api/sources/listings?summary=true&offset=100&limit=100').json()
    assert response['total'] == 205 and len(response['items']) == 100
    assert not any('description' in row or 'pending_image_urls' in row for row in response['items'])
    found = client.get('/api/sources/listings', params={'summary': True, 'q': 'CĂN HỘ 001',
        'selected_id': rows[0].id}).json()
    assert found['total'] == 1 and found['items'][0]['title'] == 'Căn hộ 001'
    assert found['selected']['id'] == rows[0].id


def test_delete_selected_and_all_preserves_campaign_image_files(saved_source):
    service, client, _ = saved_source
    rows = service.import_json(posts(3))
    image = Path(rows[0].image_paths[0])
    assert client.post('/api/sources/listings/delete', json={}).status_code == 400
    assert TestClient(server.app).post('/api/sources/listings/delete', json={'delete_all': True}).status_code == 403
    assert len(service.list_listings()) == 3
    response = client.post('/api/sources/listings/delete', json={'ids': [rows[0].id, rows[0].id, rows[1].id]})
    assert response.json()['deleted'] == 2 and len(service.list_listings()) == 1
    assert client.get(f'/api/sources/listings/{rows[0].id}/preview').status_code == 404
    assert image.is_file()  # Existing campaigns still refer to these immutable snapshots.
    assert client.post('/api/sources/listings/delete', json={'delete_all': True}).json()['deleted'] == 1
    assert service.list_listings() == []


def test_deleted_source_is_not_resurrected_by_late_download(saved_source, monkeypatch):
    service, _, _ = saved_source
    row = service.import_json(posts(1), defer_images=True)[0]
    download = service._download_snapshots
    def delete_during_download(*args, **kwargs):
        download(*args, **kwargs)
        service.delete_listings([row.id])
    monkeypatch.setattr(service, '_download_snapshots', delete_during_download)
    assert service.load_listing_images(row.id) is None
    assert service.get_listing_by_id(row.id) is None


@pytest.mark.browser
def test_fast_browser_search_paging_and_bulk_delete(saved_source):
    service, client, fetched = saved_source
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        def serve(route):
            req = route.request
            response = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
        page.route('**/*', serve)
        page.goto('http://localhost:8000/')
        assert page.locator('#json-fast').is_checked()
        page.locator('#post-json').set_input_files({'name': 'fast.json', 'mimeType': 'application/json',
            'buffer': json.dumps(posts(205)).encode()})
        page.locator('#json-import').click()
        page.wait_for_function('document.getElementById("json-summary").textContent.includes("Đã nạp 205 bài")')
        assert len(fetched) == 1 and page.locator('.photo-choice').count() == 1
        assert page.locator('#listings option').count() <= 102
        page.locator('#saved-next').click()
        page.wait_for_function('document.getElementById("saved-page").textContent.startsWith("101")')
        page.locator('#saved-search').fill('CĂN HỘ 001')
        page.locator('#saved-search-btn').click()
        page.wait_for_function('document.querySelectorAll(".saved-delete-choice").length === 1')
        page.locator('#saved-manager').evaluate('(element) => element.open = true')
        page.locator('.saved-delete-choice').check()
        page.once('dialog', lambda dialog: dialog.dismiss())
        page.locator('#saved-delete-selected').click()
        assert len(service.list_listings()) == 205
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#saved-delete-selected').click()
        page.wait_for_function('document.getElementById("notice").textContent.includes("Đã xóa 1 bài")')
        assert len(service.list_listings()) == 204
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#saved-delete-all').click()
        page.wait_for_function('document.getElementById("notice").textContent.includes("Đã xóa 204 bài")')
        assert service.list_listings() == []
        assert page.locator('#content').input_value() == ''
        assert page.locator('.photo-choice').count() == 0
        assert not errors
        browser.close()
