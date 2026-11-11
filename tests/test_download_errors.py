from unittest.mock import Mock

import pytest

from services import website_source as source


XML_ERROR = (b'<?xml version="1.0"?><Error><Code>UserProjectAccountProblem</Code>'
             b'<Message>The project to be billed is associated with a closed billing account.</Message></Error>')


def response(status, body=b'', headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.iter_content = lambda size: iter([body])
    return result


def test_google_billing_error_is_distinct_from_cloudflare():
    message = source.download_error_message(response(403, XML_ERROR))
    assert 'thanh toán' in message and 'đã đóng' in message
    assert 'Cloudflare' not in message and 'khôi phục' in message


def test_cloudflare_challenge_has_specific_message_even_with_http_200():
    message = source.download_error_message(response(200, headers={'cf-mitigated': 'challenge'}))
    assert 'Cloudflare' in message and 'công khai' in message


def test_other_access_denied_does_not_claim_billing_failure():
    message = source.download_error_message(response(403, b'AccessDenied'))
    assert 'HTTP 403' in message and 'thanh toán' not in message


def test_error_reader_stops_after_four_kilobytes():
    fetched = []
    def chunks(size):
        for i in range(100):
            fetched.append(i)
            yield b'x' * size
    item = response(403)
    item.iter_content = chunks
    source.download_error_message(item)
    assert len(fetched) == 4


def test_failed_image_reports_position_and_keeps_post(tmp_path, monkeypatch):
    service = source.WebsiteSourceService(tmp_path)
    def blocked(url, limit=None, referer=None):
        raise ValueError(source.download_error_message(response(403, XML_ERROR)))
    monkeypatch.setattr(source, 'fetch_public', blocked)
    imported = service.import_json({'posts': [{'content': 'Bài kiểm thử', 'images': ['https://photos.example/a.jpg']}]})
    assert imported[0].image_paths == [] and imported[0].media_urls == []
    assert imported[0].image_errors[0].startswith('Ảnh 1:') and 'thanh toán' in imported[0].image_errors[0]


def test_cloudflare_block_falls_back_to_browser(monkeypatch):
    from services import image_fetcher
    def blocked(url, limit=None, referer=None):
        raise image_fetcher.BlockedDownloadError('Cloudflare chặn')
    calls = []
    class FakeBrowser:
        def fetch(self, url, referer=None):
            calls.append((url, referer))
            return b'IMAGE'
        def close(self):
            calls.append('closed')
    monkeypatch.setattr(image_fetcher, 'BrowserImageFetcher', FakeBrowser)
    results = image_fetcher.download_many([('https://cf.example/a.jpg', 'https://cf.example/tin')], blocked, use_browser=True)
    assert results == [(b'IMAGE', None)]
    assert calls == [('https://cf.example/a.jpg', 'https://cf.example/tin'), 'closed']


def test_fetch_uses_browser_headers_and_flags_cloudflare(monkeypatch):
    seen = []
    class Resp:
        def __init__(self, status, headers, body=b''):
            self.status_code, self.headers, self.body = status, headers, body
        def iter_content(self, size):
            return iter([self.body])
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    def get(self, url, **kw):
        seen.append(kw['headers'])
        return Resp(403, {'server': 'cloudflare', 'cf-ray': 'x'}, b'<title>Just a moment...</title>')
    monkeypatch.setattr(source, 'public_url', lambda value, resolve=True: value)
    monkeypatch.setattr(source.requests.Session, 'get', get)
    with pytest.raises(source.BlockedDownloadError, match='Cloudflare'):
        source.fetch_public('https://cf.example/a.jpg', referer='https://cf.example/tin')
    assert 'Chrome' in seen[0]['User-Agent'] and seen[0]['Referer'] == 'https://cf.example/tin'
    assert seen[0]['Accept'].startswith('image/') and 'Referer' in seen[1]
