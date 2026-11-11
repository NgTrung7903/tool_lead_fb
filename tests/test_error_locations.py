import json

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
import pytest

from api import server
from services.group_manager import GroupManager
from services.website_source import WebsiteSourceService


@pytest.fixture
def error_app(tmp_path, monkeypatch):
    service = WebsiteSourceService(tmp_path / 'sources')
    groups = GroupManager(tmp_path / 'groups.json')
    groups.add_group('Nhóm lỗi mẫu', 'https://www.facebook.com/groups/error.fixture')
    monkeypatch.setattr(server, 'website_service', service)
    monkeypatch.setattr(server, 'group_manager', groups)
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    return service, client


def test_api_input_errors_include_semantic_locations(error_app):
    _, client = error_app
    response = client.post('/api/sources/json', json={'filename': 'x.json', 'data': [
        {'content': 'Bài đầy đủ'}, {'title': 'Thiếu nội dung'}]})
    assert response.status_code == 400
    assert response.json()['issues'][0]['location'] == ['data', 1, 'content']
    assert response.json()['issues'][0]['field'] == 'data'
    response = client.post('/api/sources/manual', json={'title': 'x', 'description': 'y', 'area_m2': -1})
    assert response.status_code == 422
    assert isinstance(response.json()['detail'], list)  # Preserve the existing HTTP contract.
    assert response.json()['issues'][0]['field'] == 'area_m2'
    response = client.post('/api/groups', json={'name': 'Nhóm', 'group_url': 'https://example.com/x'})
    assert response.status_code == 400 and response.json()['issues'][0]['field'] == 'group_url'
    response = client.post('/api/sources/json', json={'filename': 'photos.json', 'data': [
        {'content': 'Nhà đẹp', 'photos': ['https://photos.example/ok.jpg', 7]}]})
    assert response.json()['issues'][0]['location'] == ['data', 0, 'photos', 1]


def serve_page(browser, client):
    page = browser.new_page()
    def serve(route):
        req = route.request
        response = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
        route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
    page.route('**/*', serve)
    page.goto('http://localhost:8000/')
    return page


def wait_focus(page, target):
    page.wait_for_function('(id) => document.activeElement.id === id && document.getElementById(id).getAttribute("aria-invalid") === "true"', arg=target)
    assert page.locator('#active-input-issue').is_visible()


@pytest.mark.browser
def test_runtime_errors_auto_focus_groups_content_and_review_without_extra_button(error_app):
    _, client = error_app
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = serve_page(browser, client)
        page.locator('#post-json').set_input_files({'name': 'one.json', 'mimeType': 'application/json',
            'buffer': json.dumps([{'content': 'Nội dung thử'}]).encode()})
        page.locator('#json-import').click()
        page.wait_for_function('!document.getElementById("json-import").disabled')
        page.locator('#create').click()
        wait_focus(page, 'groups')
        page.locator('.group-choice').first.check()
        assert page.locator('#active-input-issue').count() == 0
        page.locator('#content').fill('')
        page.locator('#create').click()
        wait_focus(page, 'content')
        page.locator('#content').fill('Đã bổ sung nội dung')
        page.locator('#create').click()
        wait_focus(page, 'reviewed')
        assert page.locator('#notice button').count() == 0
        browser.close()


@pytest.mark.browser
def test_backend_field_error_opens_collapsed_sections_and_focuses_correct_input(error_app):
    _, client = error_app
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = serve_page(browser, client)
        # Server validation can fail after a section has been collapsed. No text
        # guessing or user click should be needed to return to the input.
        page.evaluate("""async () => {
          document.getElementById('manual-box').open = false;
          document.getElementById('other-sources').open = false;
          try { await api('/api/sources/manual', 'POST', {title:'X',description:'Y',area_m2:-1}); }
          catch (error) { notice(error, 'error'); }
        }""")
        wait_focus(page, 'manual-area')
        assert page.locator('#manual-box').get_attribute('open') is not None
        assert page.locator('#other-sources').get_attribute('open') is not None
        page.locator('#manual-area').fill('72')
        assert page.locator('#manual-area').get_attribute('aria-invalid') is None
        assert page.locator('#active-input-issue').count() == 0
        browser.close()


@pytest.mark.browser
def test_json_error_reports_original_row_after_batching_and_deleted_rows(error_app):
    service, client = error_app
    records = [{'isDeleted': True}] + [{'content': f'Bài {i}'} for i in range(201)] + [{'title': 'Thiếu nội dung'}]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = serve_page(browser, client)
        page.locator('#post-json').set_input_files({'name': 'large.json', 'mimeType': 'application/json',
            'buffer': json.dumps({'records': records}).encode()})
        page.locator('#json-import').click()
        wait_focus(page, 'post-json')
        message = page.locator('#active-input-issue').inner_text()
        assert 'Bài 203' in message and 'trường content' in message
        assert len(service.list_listings()) == 200
        browser.close()


@pytest.mark.browser
def test_unknown_error_does_not_focus_an_unrelated_field(error_app):
    _, client = error_app
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = serve_page(browser, client)
        page.evaluate("notice(new Error('Lỗi hệ thống chưa xác định'), 'error')")
        assert page.locator('#notice').inner_text() == 'Lỗi hệ thống chưa xác định'
        assert page.locator('.input-issue-focus').count() == 0
        browser.close()
