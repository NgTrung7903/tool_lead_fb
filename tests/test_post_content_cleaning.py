import json
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
import pytest

from api import server
from services.website_source import WebsiteSourceService, clean_post_html


@pytest.mark.parametrize('raw,expected', [
    ('<p>Nhà thật – thông tin thật<br><br>- DT: 5.6x14m; CN 72m²<br>- KC: 5 tầng.</p>',
     'Nhà thật – thông tin thật\n\n- DT: 5.6x14m; CN 72m²\n- KC: 5 tầng.'),
    ('<p>Giá <strong>20 tỷ TL</strong> &amp; phí&nbsp;quản lý</p><p>Hẹn xem nhà</p>',
     'Giá 20 tỷ TL & phí quản lý\n\nHẹn xem nhà'),
    ('<ul><li>2 phòng ngủ</li><li>2 WC</li></ul>', '- 2 phòng ngủ\n- 2 WC'),
    ('&lt;p&gt;Nhà đẹp&lt;br /&gt;72m²&lt;/p&gt;', 'Nhà đẹp\n72m²'),
    ('<style>.x{color:red}</style><p>Nhà đẹp</p><script>alert(1)</script><iframe>Quảng cáo</iframe>', 'Nhà đẹp'),
    ('Giá < 3 tỷ, diện tích > 60m²\r\nGiữ nguyên  khoảng cách\r\n\r\nLiên hệ',
     'Giá < 3 tỷ, diện tích > 60m²\r\nGiữ nguyên  khoảng cách\r\n\r\nLiên hệ'),
    ('AT&T &notary <PRIVATE_PERSON>', 'AT&T &notary <PRIVATE_PERSON>'),
    ('<p>Nhắn <PRIVATE_PERSON> để xem nhà</p>', 'Nhắn <PRIVATE_PERSON> để xem nhà'),
])
def test_html_to_post_text_preserves_content_and_layout(raw, expected):
    assert clean_post_html(raw) == expected
    assert clean_post_html(expected) == expected


@pytest.fixture
def clean_source(tmp_path, monkeypatch):
    service = WebsiteSourceService(tmp_path / 'source')
    monkeypatch.setattr(server, 'website_service', service)
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    return service, client


def test_previously_saved_html_is_cleaned_without_reimport_or_identity_change(clean_source):
    service, client = clean_source
    raw = '<p>Nhà Quận 3<br>Giá <b>20 tỷ</b>, 72m².</p>'
    payload = [{'title': 'Nhà Q3', 'content': raw}]
    row = service.import_json(payload)[0]
    preview = client.get(f'/api/sources/listings/{row.id}/preview').json()
    assert preview['formatted_text'] == 'Nhà Quận 3\nGiá 20 tỷ, 72m².'
    assert service.get_listing_by_id(row.id).post_text == raw
    assert service.import_json(payload)[0].id == row.id
    assert len(service.list_listings()) == 1
    blocked = client.post('/api/workflow/campaigns', json={'listing_id': row.id,
        'target_group_ids': ['group'], 'custom_content': raw, 'preview_token': preview['preview_token'],
        'reviewed': True, 'image_indices': []})
    assert blocked.status_code == 400 and 'HTML' in blocked.json()['detail']
    result = client.post('/api/sources/clean-content', json={'content': raw}).json()
    assert result == {'content': preview['formatted_text'], 'changed': True}


@pytest.mark.browser
def test_browser_cleans_imported_and_pasted_html_and_requires_review(clean_source):
    _, client = clean_source
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def serve(route):
            req = route.request
            response = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
        page.route('**/*', serve)
        page.goto('http://localhost:8000/')
        payload = [{'title': 'Nhà đẹp', 'content': '<p>Nhà đẹp<br>72m² – 20 tỷ</p>'}]
        page.locator('#post-json').set_input_files({'name': 'html.json', 'mimeType': 'application/json',
            'buffer': json.dumps(payload).encode()})
        page.locator('#json-import').click()
        page.wait_for_function('!document.getElementById("json-import").disabled')
        assert page.locator('#content').input_value() == 'Nhà đẹp\n72m² – 20 tỷ'
        page.locator('#content').fill('<p>Dòng 1<br><br>Dòng 2 &amp; giá &lt; 3 tỷ</p>')
        page.locator('#reviewed').check()
        page.locator('#clean-content').click()
        page.wait_for_function('document.getElementById("content").value === "Dòng 1\\n\\nDòng 2 & giá < 3 tỷ"')
        assert not page.locator('#reviewed').is_checked()
        assert not errors
        browser.close()
