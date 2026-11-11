"""Public Revoland pages and JSON use the selected property's own fields."""
from io import BytesIO
import json
import socket

from fastapi.testclient import TestClient
from PIL import Image
from playwright.sync_api import sync_playwright
import pytest

from api import server
from services import website_source as source


PROPERTY_ID = 'a' * 24
SOURCE_URL = f'https://www.revoland.vn/mua-nha/tin-minh-hoa/{PROPERTY_ID}'


def property_record(**changes):
    return {
        'id': PROPERTY_ID, 'propertyCode': 'TIN-123',
        'title': 'Căn hộ dịch vụ đang khai thác', 'description': '<p>Hẻm rộng.</p><p>Liên hệ 0900000000.</p>',
        'transactionType': 'ForSale', 'type': 'House', 'status': 'PUBLISH',
        'location': {'address': 'Phường Xuân Hòa, TP.HCM'},
        'propertyDetails': {'landArea': 52, 'usableArea': 300, 'bedrooms': 6, 'bathrooms': 6, 'floorNumber': 6},
        'priceDetails': {'salePrice': 12000000000, 'rentalPrice': None, 'currency': 'VND'},
        'imageUrls': ['https://photos.example/1.jpg', 'https://photos.example/2.jpg'],
        'privateNote': 'PRIVATE_NOTE', 'company': {'phone': 'PRIVATE_PHONE', 'invitationLink': 'PRIVATE_INVITE'},
        **changes,
    }


def flight_page(record):
    other = property_record(id='b' * 24, title='Bài gợi ý')
    frame = 'a:["$","$L0",null,' + json.dumps({'suggested': other, 'property': record}, ensure_ascii=False) + ']\n'
    # The property's JSON can straddle several Next.js script chunks.
    cut = len(frame) // 2
    return ''.join('<script>self.__next_f.push(' + json.dumps([1, chunk]) + ')</script>'
                   for chunk in (frame[:cut], frame[cut:]))


@pytest.fixture
def importer(tmp_path, monkeypatch):
    monkeypatch.setattr(source.socket, 'getaddrinfo',
                        lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 443))])
    image = BytesIO()
    Image.new('RGB', (32, 24), 'navy').save(image, 'PNG')
    state = {'body': flight_page(property_record()), 'type': 'text/html', 'fetched': []}

    def fetch(url, max_bytes=None, referer=None):
        state['fetched'].append(url)
        if url.startswith('https://photos.example/'):
            return image.getvalue(), url, 'image/png'
        return state['body'].encode(), url, state['type']

    monkeypatch.setattr(source, 'fetch_public', fetch)
    return source.WebsiteSourceService(tmp_path / 'sources'), state


def test_page_import_composes_exact_property_and_downloads_images(importer):
    service, state = importer
    listing = service.import_url(SOURCE_URL + '?utm_source=share')[0]
    content = service.provider(listing, [0, 1]).format_post_content(listing)
    assert listing.code == 'TIN-123' and listing.source_url == SOURCE_URL
    assert listing.price_text == '12 tỷ' and listing.area_m2 == 52
    assert 'Diện tích đất: 52 m²' in content and 'Diện tích sử dụng: 300 m²' in content
    assert 'Phòng ngủ: 6' in content and 'WC: 6' in content
    assert 'Hẻm rộng.\n\nLiên hệ 0900000000.' in content
    assert all(value not in content for value in ('PRIVATE_', 'Bài gợi ý', '<p>', 'Số tầng'))
    assert len(listing.image_paths) == len(listing.image_hashes) == 2
    assert set(state['fetched'][1:]) == set(property_record()['imageUrls'])
    updated = service.import_url(SOURCE_URL)[0]
    assert updated.id == listing.id and len(service.list_listings()) == 1


def test_json_api_envelope_supports_rent_and_missing_optional_fields(importer):
    service, state = importer
    state['type'] = 'application/json'
    state['body'] = json.dumps({'code': 200, 'status': True, 'data': property_record(
        title='Studio có ban công', transactionType='ForRent',
        propertyDetails={'landArea': 20, 'usableArea': 20, 'bedrooms': None, 'bathrooms': 1},
        priceDetails={'salePrice': None, 'rentalPrice': 3500000, 'currency': 'VND'})})
    listing = service.import_url('https://api.example/property?id=' + PROPERTY_ID)[0]
    assert listing.price_text == '3,5 triệu/tháng'
    assert listing.source_url.endswith('?id=' + PROPERTY_ID)
    assert 'Giá thuê: 3,5 triệu/tháng' in listing.post_text
    assert 'Phòng ngủ' not in listing.post_text


def test_json_file_envelope_generates_content_and_defers_images(importer):
    service, _ = importer
    listing = service.import_json({'code': 200, 'status': True, 'data': property_record()}, defer_images=True)[0]
    assert listing.code == 'TIN-123' and listing.post_text.startswith('🏡 Căn hộ dịch vụ')
    assert 'Giá bán: 12 tỷ' in listing.post_text
    assert listing.pending_image_urls == property_record()['imageUrls']
    assert listing.image_paths == []
    loaded = service.load_listing_images(listing.id)
    assert len(loaded.image_paths) == 2


def test_different_property_is_rejected_instead_of_using_suggestions(importer):
    service, state = importer
    state['body'] = flight_page(property_record(id='c' * 24))
    with pytest.raises(ValueError, match='Không nhận diện'):
        service.import_url(SOURCE_URL)
    assert service.list_listings() == []
    with pytest.raises(ValueError, match='khác mã tin'):
        source.parse_revoland_property(property_record(id='c' * 24), SOURCE_URL)


@pytest.mark.parametrize('field,value', [
    ('title', []), ('propertyDetails', ['bad']), ('priceDetails', ['bad']),
    ('location', ['bad']), ('imageUrls', ['https://photos.example/1.jpg', 3]),
])
def test_invalid_property_fields_fail_before_saving(importer, field, value):
    service, state = importer
    state['body'] = flight_page(property_record(**{field: value}))
    with pytest.raises(ValueError):
        service.import_url(SOURCE_URL)
    assert service.list_listings() == []


def test_unpublished_property_stays_unavailable(importer):
    service, state = importer
    state['body'] = flight_page(property_record(status='DRAFT'))
    assert service.import_url(SOURCE_URL)[0].status == 'unavailable'


def test_remote_property_cannot_import_local_files_as_images(importer):
    service, state = importer
    state['body'] = flight_page(property_record(imageUrls=['file:///C:/private/photo.jpg']))
    with pytest.raises(ValueError, match='HTTP'):
        service.import_url(SOURCE_URL)
    assert state['fetched'] == [SOURCE_URL] and service.list_listings() == []


def test_json_response_cannot_override_the_requested_property_with_its_own_url(importer):
    service, state = importer
    state['type'] = 'application/json'
    state['body'] = json.dumps({'data': property_record(
        id='b' * 24, source_url=SOURCE_URL.replace(PROPERTY_ID, 'b' * 24))})
    with pytest.raises(ValueError, match='khác mã tin'):
        service.import_url(SOURCE_URL)
    assert service.list_listings() == []


@pytest.mark.parametrize('amount,expected', [(None, 'Chưa có thông tin giá'), (0, 'Chưa có thông tin giá'),
                                            (1234567890, '1,23456789 tỷ')])
def test_missing_price_and_exact_price_are_not_invented(amount, expected):
    row = property_record(priceDetails={'salePrice': amount})
    assert source.parse_revoland_property(row)['price_text'] == expected


@pytest.mark.browser
def test_primary_link_input_previews_article_and_reports_source_errors(importer, monkeypatch):
    service, state = importer
    monkeypatch.setattr(server, 'website_service', service)
    client = TestClient(server.app, base_url='http://localhost:8000', headers={'X-Revoland-Client': 'local'})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        errors = []

        def serve(route):
            request = route.request
            assert request.url.startswith('http://localhost:8000/')
            response = client.request(request.method, request.url, headers=request.all_headers(), content=request.post_data)
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)

        context.route('**/*', serve)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://localhost:8000/')
        assert page.locator('#source-url').is_visible()
        assert not page.locator('#other-sources').evaluate('e => e.open')
        page.locator('#source-url').fill(SOURCE_URL)
        page.get_by_role('button', name='Lấy tin & soạn nội dung', exact=True).click()
        page.wait_for_function("document.querySelector('#content').value.includes('Giá bán: 12 tỷ')")
        assert page.locator('.photo-choice').count() == 2
        assert 'PRIVATE_' not in page.locator('#content').input_value()
        page.locator('#content').fill('Nội dung đã được người dùng sửa và duyệt.')
        assert not page.locator('#reviewed').is_checked()
        state['body'] = flight_page(property_record(id='c' * 24))
        page.locator('#import').click()
        page.wait_for_function("document.activeElement.id === 'source-url'")
        assert page.locator('#source-url').get_attribute('aria-invalid') == 'true'
        assert page.locator('#content').input_value() == 'Nội dung đã được người dùng sửa và duyệt.'
        assert errors == []
        context.close()
        browser.close()
