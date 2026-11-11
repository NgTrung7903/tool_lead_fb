from io import BytesIO
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from playwright.sync_api import sync_playwright

from api import server
from services import website_source as source


CONTENT = 'Bán căn hộ A\r\n72 m², giá 2,85 tỷ.\r\nĐang làm sổ, chưa gồm phí. Liên hệ 0900000000'
POSTS = {'posts': [{'title': 'Căn hộ A', 'content': CONTENT,
                    'images': ['https://photos.example/a.jpg', 'https://photos.example/b.jpg']},
                   {'title': 'Bài B', 'content': 'Nội dung bài thứ hai, không có ảnh.', 'images': []}]}


@pytest.fixture
def json_source(tmp_path, monkeypatch):
    service = source.WebsiteSourceService(tmp_path / 'source')
    image = BytesIO()
    Image.new('RGB', (80, 60), '#abcabc').save(image, 'PNG')
    fetched = []
    def fetch(url, limit=None, referer=None):
        fetched.append(url)
        return image.getvalue(), url, 'image/png'
    monkeypatch.setattr(source, 'fetch_public', fetch)
    monkeypatch.setattr(server, 'website_service', service)
    return service, fetched


@pytest.mark.parametrize('wrapper', ['posts', 'listings', 'data', 'array', 'single'])
def test_json_preserves_content_downloads_images_and_reimport_is_stable(json_source, wrapper):
    service, fetched = json_source
    rows = POSTS['posts']
    payload = rows[0] if wrapper == 'single' else rows if wrapper == 'array' else {wrapper: rows}
    imported = service.import_json(payload)
    assert service.provider(imported[0], [0, 1]).format_post_content(imported[0]) == CONTENT
    assert len(imported[0].image_paths) == 2
    assert sorted(fetched[:2]) == sorted(POSTS['posts'][0]['images'])
    assert imported[0].media_urls == POSTS['posts'][0]['images']
    assert all(source.Path(p).is_file() for p in imported[0].image_paths)
    assert service.import_json(payload)[0].id == imported[0].id
    assert len(service.list_listings()) == len(imported)


@pytest.mark.parametrize('payload', [[], {'wrong': []}, ['text'], [{'content': ' '}],
    [{'content': 123}], [{'content': 'x', 'images': 123}], [{'content': 'x', 'images': [123]}]])
def test_bad_json_is_rejected_without_saving_or_fetching(json_source, payload):
    service, fetched = json_source
    with pytest.raises(ValueError):
        service.import_json(payload)
    assert service.list_listings() == [] and fetched == []


def test_json_has_no_post_image_or_length_limits(json_source):
    service, fetched = json_source
    long_text = 'Nội dung rất dài. ' * 10000
    posts = [{'content': f'Bài số {i}\n{long_text}', 'title': 'T' * 1000,
              'images': [f'https://photos.example/{i}-{j}.jpg' for j in range(20)]} for i in range(35)]
    imported = service.import_json({'posts': posts})
    assert len(imported) == 35
    assert all(len(row.image_paths) == 20 and not row.image_errors for row in imported)
    assert len(fetched) == 35 * 20
    assert len(imported[0].post_text) > 50000


def test_json_accepts_alias_keys_base64_local_files_and_dedupes(json_source, tmp_path):
    service, fetched = json_source
    local = tmp_path / 'anh.png'
    Image.new('RGB', (30, 20), '#123456').save(local)
    buffer = BytesIO()
    Image.new('RGBA', (30, 20), (1, 2, 3, 128)).save(buffer, 'PNG')
    data_uri = 'data:image/png;base64,' + source.base64.b64encode(buffer.getvalue()).decode()
    post = {'text': 'Bài alias', 'photos': [{'url': 'https://photos.example/x.webp'}, str(local), local.as_uri(), data_uri]}
    imported = service.import_json([post, post])
    assert len(imported) == 1
    assert len(imported[0].image_paths) == 4 and not imported[0].image_errors
    assert imported[0].media_urls[-1] == 'embedded://photo/3'
    assert fetched == ['https://photos.example/x.webp']


def test_image_failure_keeps_post_and_reports_each_image(json_source, monkeypatch):
    service, _ = json_source
    good = BytesIO()
    Image.new('RGB', (10, 10)).save(good, 'PNG')
    def fetch(url, limit=None, referer=None):
        if url.endswith('b.jpg'):
            raise ValueError('Không tải được ảnh')
        return good.getvalue(), url, 'image/png'
    monkeypatch.setattr(source, 'fetch_public', fetch)
    imported = service.import_json({'posts': [POSTS['posts'][1], POSTS['posts'][0],
                                              {'content': 'Ảnh mất', 'images': ['file:///khong-ton-tai.jpg']}]})
    assert len(imported) == 3
    assert imported[1].media_urls == ['https://photos.example/a.jpg'] and len(imported[1].image_paths) == 1
    assert imported[1].image_errors == ['Ảnh 2: Không tải được ảnh']
    assert imported[2].image_paths == [] and 'Không tìm thấy file ảnh' in imported[2].image_errors[0]
    assert len(service.list_listings()) == 3


def test_html_instead_of_image_is_reported(json_source, monkeypatch):
    service, _ = json_source
    monkeypatch.setattr(source, 'fetch_public',
                        lambda url, limit=None, referer=None: (b'<!DOCTYPE html><title>Just a moment...</title>', url, 'text/html'))
    imported = service.import_json([{'content': 'x', 'images': ['https://cf.example/a.jpg']}])
    assert imported[0].image_paths == [] and 'Cloudflare' in imported[0].image_errors[0]


def test_json_api_preview_and_sample(json_source):
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    imported = client.post('/api/sources/json', json={'filename': 'posts.json', 'data': POSTS})
    assert imported.status_code == 200, imported.text
    assert len(imported.json()) == 2 and 'image_paths' not in imported.json()[0]
    preview = client.get('/api/sources/listings/' + imported.json()[0]['id'] + '/preview').json()
    assert preview['formatted_text'] == CONTENT and len(preview['media_urls']) == 2
    assert client.get(preview['media_urls'][0]).status_code == 200
    assert client.post('/api/sources/json', json={'filename': 'posts.txt', 'data': POSTS}).status_code == 400
    assert TestClient(server.app).post('/api/sources/json', json={'filename': 'posts.json', 'data': POSTS}).status_code == 403
    sample = client.get('/assets/posts-example.json')
    assert sample.status_code == 200
    assert client.post('/api/sources/json', json={'filename': 'sample.json', 'data': sample.json()}).status_code == 200


@pytest.mark.browser
def test_browser_json_import_and_article_selection(json_source):
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def serve(route):
            req = route.request
            assert req.url.startswith('http://localhost:8000/')
            r = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
            route.fulfill(status=r.status_code, headers=dict(r.headers), body=r.content)
        page.route('**/*', serve)
        page.goto('http://localhost:8000/')
        page.locator('#post-json').set_input_files({'name': 'bai_dang.json', 'mimeType': 'application/json',
                                                  'buffer': json.dumps(POSTS, ensure_ascii=False).encode()})
        page.locator('#json-fast').uncheck()
        page.locator('#json-import').click()
        page.wait_for_function("document.getElementById('json-summary').textContent.includes('Đã nạp 2 bài')")
        assert page.locator('#content').input_value() == CONTENT.replace('\r\n', '\n')
        assert page.locator('.photo-choice').count() == 2
        page.locator('#listings').select_option(label='Bài B')
        page.wait_for_function("document.getElementById('content').value.includes('thứ hai')")
        assert page.locator('.photo-choice').count() == 0
        page.locator('#reviewed').check()
        page.locator('#content').fill('Nội dung chỉnh tay')
        assert not page.locator('#reviewed').is_checked()
        assert page.locator('#rewrite').count() == 0 and page.locator('#text-form').count() == 0
        assert page.locator('#folder-form').count() == 0
        # UTF-16LE BOM JSON (như file xuất từ Windows PowerShell Out-File) cũng nạp được ngay
        utf16_payload = b'\xff\xfe' + json.dumps([{'title': None, 'content': 'Bài UTF16\nDòng 2', 'images': ''}], ensure_ascii=False).encode('utf-16-le')
        page.locator('#post-json').set_input_files({'name': 'utf16.json', 'mimeType': 'application/json', 'buffer': utf16_payload})
        page.locator('#json-fast').uncheck()
        page.locator('#json-import').click()
        page.wait_for_function("document.getElementById('content').value.includes('Bài UTF16')")
        assert not errors
        browser.close()


def test_json_supports_quinland_schema_string_images_and_nullable_fields(json_source):
    service, fetched = json_source
    quinland_row = {
        '_id': {'$oid': '65f000000000000000000001'},
        'title': 'Căn hộ Vinhomes 2PN',
        'description': 'View công viên thoáng mát.',
        'transactionType': 'ForSale',
        'type': 'Apartment',
        'propertyDetails': {'buildingArea': 68, 'bedrooms': 2, 'bathrooms': 2},
        'priceDetails': {'salePrice': {'$numberLong': '3200000000'}},
        'location': {'ward': 'Long Bình', 'city': 'TP. Thủ Đức'},
        'images': ['https://photos.example/q1.jpg'],
    }
    relaxed_row = {
        'title': None,
        'content': 'Nhà mặt tiền Quận 3\nGiá 18 tỷ',
        'source_url': 'http://bad-port.example:9999/ignored',
        'images': 'https://photos.example/s1.jpg, https://photos.example/s2.jpg\nhttps://photos.example/s3.jpg',
    }
    imported = service.import_json([quinland_row, relaxed_row, {'isDeleted': True, 'content': 'Đã xóa'}])
    assert len(imported) == 2
    assert '3,2 tỷ' in service.provider(imported[0], [0]).format_post_content(imported[0])
    assert imported[1].title == 'Nhà mặt tiền Quận 3' and len(imported[1].image_paths) == 3
    assert len(fetched) == 4


@pytest.mark.browser
def test_browser_image_fetcher_solves_cloudflare_and_ignores_favicon(tmp_path):
    from services.image_fetcher import BrowserImageFetcher
    real_img = BytesIO()
    Image.new('RGB', (64, 48), '#2266aa').save(real_img, 'JPEG')
    decoy_icon = BytesIO()
    Image.new('RGB', (16, 16), '#ff0000').save(decoy_icon, 'PNG')
    cleared = {'ok': False}
    hits = []

    with BrowserImageFetcher(profile_dir=tmp_path / 'cf-profile', headless_wait=8.0, visible_wait=0.1) as fetcher:
        ctx = fetcher._open(True)

        def handle(route):
            url = route.request.url
            hits.append((url, route.request.is_navigation_request()))
            if url.endswith('/favicon.ico'):
                route.fulfill(status=200, content_type='image/png', body=decoy_icon.getvalue())
                return
            if not cleared['ok']:
                cleared['ok'] = True
                html = (
                    '<!doctype html><html><head><title>Just a moment...</title>'
                    '<link rel="icon" href="/favicon.ico">'
                    '<script>setTimeout(() => location.reload(), 250);</script></head>'
                    '<body>Verifying you are human...</body></html>'
                )
                route.fulfill(status=403, headers={'cf-mitigated': 'challenge', 'content-type': 'text/html'}, body=html.encode())
                return
            route.fulfill(status=200, headers={'content-type': 'image/jpeg', 'access-control-allow-origin': '*'}, body=real_img.getvalue())

        ctx.route('https://cf-cdn.example/**', handle)
        first = fetcher._try_page(ctx, 'https://cf-cdn.example/anh-1.jpg', 'https://cf-cdn.example/tin-1', 8.0)
        second = fetcher._try_page(ctx, 'https://cf-cdn.example/anh-2.jpg', 'https://cf-cdn.example/tin-1', 8.0)
        assert first == real_img.getvalue()
        assert second == real_img.getvalue()
        with Image.open(BytesIO(first)) as im:
            assert im.size == (64, 48)


def test_large_import_saves_snapshots_before_next_download_batch(json_source, monkeypatch):
    service, _ = json_source
    original = source.download_many
    batches = []
    def download(refs, *args, **kwargs):
        # Previously downloaded bodies must be on disk before the next batch starts.
        assert len(list(service.root.glob('images/*/*.jpg'))) == sum(batches)
        batches.append(len(refs))
        return original(refs, *args, **kwargs)
    monkeypatch.setattr(source, 'download_many', download)
    refs = [f'https://photos.example/{i}.jpg' for i in range(70)]
    row = service.import_json({'content': 'Large import', 'images': refs})[0]
    assert len(batches) > 1 and max(batches) <= source.IMAGE_DOWNLOAD_BATCH_SIZE
    assert row.media_urls == refs and len(row.image_paths) == 70
    assert not row.image_errors


@pytest.mark.browser
@pytest.mark.parametrize('interrupt', [False, True])
def test_large_json_import_batches_and_preserves_completed_posts(json_source, interrupt):
    service, _ = json_source
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    posts = [{'content': f'Batch post {i}', 'images': [f'https://photos.example/{i}.jpg']} for i in range(21)]
    posts.insert(3, {'isDeleted': True})
    sizes = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        def serve(route):
            req = route.request
            if req.url.endswith('/api/sources/json'):
                sizes.append(len(json.loads(req.post_data)['data']))
                if interrupt and len(sizes) == 2:
                    route.fulfill(status=503, content_type='application/json', body='{"detail":"Connection interrupted"}')
                    return
            r = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
            route.fulfill(status=r.status_code, headers=dict(r.headers), body=r.content)
        page.route('**/*', serve)
        page.goto('http://localhost:8000/')
        page.locator('#post-json').set_input_files({'name': 'large.json', 'mimeType': 'application/json',
            'buffer': json.dumps({'records': posts}).encode()})
        page.locator('#json-fast').uncheck()
        page.locator('#json-import').click()
        expected = 'Đã lưu 20 bài trước khi bị gián đoạn' if interrupt else 'Đã nạp 21 bài, 21 ảnh'
        page.wait_for_function('(text) => document.getElementById("json-summary").textContent.includes(text)', arg=expected)
        page.wait_for_function('!document.getElementById("json-import").disabled')
        page.locator('.photo-choice').first.wait_for(state='visible')
        assert sizes == [20, 1]
        assert len(service.list_listings()) == (20 if interrupt else 21)
        assert page.locator('.photo-choice').count() == 1
        browser.close()
