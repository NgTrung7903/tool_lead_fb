from io import BytesIO
from unittest.mock import Mock

import pytest
from PIL import Image

from services.revoland_service import RevolandService, RevolandAPIError, SAMPLE_LISTINGS


def response(data=None, status=200):
    res = Mock(status_code=status)
    res.json.return_value = data
    return res


@pytest.fixture
def live():
    service = RevolandService()
    service.config['revoland_mock_mode'] = False
    return service


@pytest.mark.parametrize('status', [401,403,500])
def test_http_error_never_falls_back(live, monkeypatch, status):
    monkeypatch.setattr('services.revoland_service.requests.get', Mock(return_value=response(status=status)))
    with pytest.raises(RevolandAPIError, match=str(status)):
        live.get_listings()


@pytest.mark.parametrize('payload', [[SAMPLE_LISTINGS[0]], {'data':[SAMPLE_LISTINGS[0]]}, {'listings':[SAMPLE_LISTINGS[0]]}])
def test_supported_envelopes(live, monkeypatch, payload):
    monkeypatch.setattr('services.revoland_service.requests.get', Mock(return_value=response(payload)))
    assert [x.id for x in live.get_listings()] == ['rev_listing_001']


def test_empty_is_empty(live, monkeypatch):
    monkeypatch.setattr('services.revoland_service.requests.get', Mock(return_value=response({'data':[]})))
    assert live.get_listings() == []


def test_pagination(live, monkeypatch):
    get = Mock(side_effect=[response({'data':[SAMPLE_LISTINGS[0]],'meta':{'last_page':2}}),
                            response({'data':[SAMPLE_LISTINGS[1]],'meta':{'last_page':2}})])
    monkeypatch.setattr('services.revoland_service.requests.get', get)
    assert len(live.get_listings()) == 2
    assert get.call_args.kwargs['params'] == {'page':2}


def test_bad_schema_is_error(live, monkeypatch):
    monkeypatch.setattr('services.revoland_service.requests.get', Mock(return_value=response({'data':[{'id':'only'}]})))
    with pytest.raises(RevolandAPIError): live.get_listings()


def test_no_invented_legal_claim(live):
    from models.schema import PropertyListing
    listing = PropertyListing(**{**SAMPLE_LISTINGS[0], 'description':'API description'})
    assert 'Pháp lý:' not in live.format_post_content(listing)
    listing.legal_status = 'Đang chờ giấy tờ'
    assert listing.legal_status in live.format_post_content(listing)


def test_no_invented_rooms_or_area_when_missing(live):
    from models.schema import PropertyListing
    sparse = PropertyListing(id='s1', code='S1', title='Đất nền', price_text='3 tỷ', location='Thủ Đức', description='Đất trống')
    text = live.format_post_content(sparse)
    assert 'Phòng ngủ' not in text and 'WC' not in text and 'Diện tích' not in text


def test_all_images_or_error(live, monkeypatch, tmp_path):
    from models.schema import PropertyListing
    monkeypatch.setattr('services.revoland_service.TEMP_IMAGE_DIR', tmp_path)
    listing = PropertyListing(**SAMPLE_LISTINGS[0])
    res = response(status=404); res.__enter__ = Mock(return_value=res); res.__exit__ = Mock(return_value=False)
    monkeypatch.setattr('services.revoland_service.requests.get', Mock(return_value=res))
    with pytest.raises(RevolandAPIError, match='đầy đủ ảnh'): live.download_listing_images(listing)


def test_download_validates_images_and_keeps_all(live, monkeypatch, tmp_path):
    from models.schema import PropertyListing
    monkeypatch.setattr('services.revoland_service.TEMP_IMAGE_DIR', tmp_path)
    stream = BytesIO(); Image.new('RGB', (20,20), 'red').save(stream,'PNG')
    res = response(); res.iter_content.return_value = [stream.getvalue()]
    res.__enter__ = Mock(return_value=res); res.__exit__ = Mock(return_value=False)
    monkeypatch.setattr('services.revoland_service.requests.get', Mock(return_value=res))
    listing = PropertyListing(**{**SAMPLE_LISTINGS[0], 'id':'../../escape', 'media_urls':['https://example.com/' + str(i) for i in range(6)]})
    paths = live.download_listing_images(listing)
    assert len(paths) == 6
    from pathlib import Path
    assert all(Path(p).is_relative_to(tmp_path) for p in paths)
