"""End-to-end lead filtering uses offline Facebook fixtures, never real accounts."""
from contextlib import nullcontext
from io import BytesIO
import json
from pathlib import Path
import threading
from unittest.mock import Mock
from types import SimpleNamespace

from fastapi.testclient import TestClient
import openpyxl
import pytest
from playwright.sync_api import sync_playwright

from api import server
from services.facebook_browser import profile_operation
from services.facebook_comment_collector import FacebookCommentCollector, normalize_post_url
from services.lead_filter_service import LeadFilterService, filter_records, registry_inventory
from services.storage import ResourceBusyError


URL = 'https://www.facebook.com/groups/test/posts/123'
ROWS = [{'id': 'c1', 'fb_user_name': '<img src=x onerror="window.injected=1">',
         'raw_content': 'Cần mua căn này 0912345678', 'source_url': URL,
         'comment_url': URL + '?comment_id=c1'},
        {'id': 'c2', 'fb_user_name': 'B', 'raw_content': 'xin giá', 'source_url': URL},
        {'id': 'c3', 'fb_user_name': 'C', 'raw_content': 'không mua nữa', 'source_url': URL}]


@pytest.mark.parametrize('value', ['http://facebook.com/a/posts/123', 'https://facebook.com.evil.test/a/posts/123',
    'https://evil.test/a/posts/123', 'https://facebook.com/groups/test',
    'https://facebook.com/share/r/123', 'https://facebook.com/share/v/123',
    'https://facebook.com/share/p/', 'https://facebook.com/share/p/123/extra',
    'https://x:pass@facebook.com/a/posts/123', 'https://facebook.com:999/a/posts/123'])
def test_only_facebook_post_urls(value):
    with pytest.raises(ValueError): normalize_post_url(value)


def test_post_url_normalization_and_registry_inventory():
    assert normalize_post_url('https://m.facebook.com/groups/test/posts/123/?fbclid=tracking') == URL
    assert normalize_post_url('https://facebook.com/permalink.php?id=2&story_fbid=1&comment_id=3') == 'https://www.facebook.com/permalink.php?story_fbid=1&id=2'
    registry = registry_inventory()
    assert len(registry) == 5
    assert [r['rule_count'] for r in registry] == [10, 9, 6, 6, 23]
    assert all(r['token_count'] == sum(len(rule['tokens']) for rule in r['rules']) for r in registry)
    assert registry[-1]['rules'][0]['score'] is None
    other_demand = next(r for r in registry[2]['rules'] if r['key'] == 'wrong_demand_type')
    assert other_demand['review_only'] and other_demand['score'] is None
    contact = next(r for r in registry[0]['rules'] if r['key'] == 'contact_sharing')
    assert contact['requires_contact'] and contact['family'] == 'contact'


@pytest.mark.parametrize('path', ['share/p/AbC123', 'share/1AbC123'])
def test_share_post_url_normalization(path):
    value = f'https://m.facebook.com/{path}/?mibextid=tracking#fragment'
    assert normalize_post_url(value) == f'https://www.facebook.com/{path}'
    with pytest.raises(ValueError):
        normalize_post_url(value, allow_share=False)


def test_filter_explains_classification_without_claiming_crm_creation():
    result = filter_records(ROWS)
    assert result['summary'] == {'total': 3, 'LEAD_POTENTIAL': 1, 'NEEDS_REVIEW': 1, 'IGNORE': 1}
    lead = result['records'][0]
    assert lead['contacts']['primary_phone'] == '0912345678'
    assert lead['registry_version'] == '1.4.0'
    assert not any('Tự động tạo Lead' in reason for reason in lead['reasons'])
    assert lead['comment_url'].endswith('comment_id=c1')


def test_truncated_comment_does_not_become_confirmed_potential_lead():
    result = filter_records([{**ROWS[0], 'text_truncated': True}])
    assert result['records'][0]['classification'] == 'NEEDS_REVIEW'
    assert 'cắt ngắn' in result['records'][0]['reasons'][0]


class FixtureCollector:
    def collect(self, url, limit, stop, progress):
        progress(ROWS[:limit])
        return 'partial', ROWS[:limit], 'Fixture: chưa xác nhận lấy đủ.'


def completed_service(tmp_path):
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', FixtureCollector())
    run = service.start(URL)
    service._thread.join(timeout=5)
    assert not service._thread.is_alive()
    return service, run['id']


def test_collection_persists_and_exports_selected_classification(tmp_path, monkeypatch):
    service, run_id = completed_service(tmp_path)
    restored = LeadFilterService(service.data_dir, service.profile_dir)
    assert restored.get(run_id)['records'][0]['contacts']['primary_phone'] == '0912345678'
    assert restored.list_runs()[0]['status'] == 'partial'
    monkeypatch.setattr(server, 'lead_service', restored)
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    response = client.get(f'/api/leads/runs/{run_id}/excel?classification=LEAD_POTENTIAL')
    workbook = openpyxl.load_workbook(BytesIO(response.content))
    assert workbook.active.max_row == 2
    assert workbook.active['E2'].value == '0912345678'
    assert workbook.active['C2'].value == 'LEAD_POTENTIAL'
    assert client.get(f'/api/leads/runs/{run_id}/excel?classification=bad').status_code == 400
    assert client.get('/api/leads/runs/../config').status_code != 200


def test_stop_profile_exclusivity_and_partial_failure(tmp_path):
    ready = threading.Event()
    class WaitCollector:
        def collect(self, url, limit, stop, progress):
            progress(ROWS[:1])
            ready.set()
            assert stop.wait(5)
            raise RuntimeError('fixture browser closed')
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', WaitCollector())
    run = service.start(URL)
    assert ready.wait(5)
    with pytest.raises(ResourceBusyError): service.start(URL)
    with pytest.raises(ResourceBusyError):
        with profile_operation(service.profile_dir): pass
    service.stop(run['id'])
    service._thread.join(5)
    saved = service.get(run['id'])
    assert saved['status'] == 'failed' and saved['summary']['total'] == 1
    with profile_operation(service.profile_dir): pass


def test_restart_reports_interrupted_run(tmp_path):
    service, run_id = completed_service(tmp_path)
    path = service._path(run_id)
    saved = service.get(run_id)
    saved['status'] = 'running'
    path.write_text(json.dumps(saved), encoding='utf-8')
    assert LeadFilterService(service.data_dir).list_runs()[0]['status'] == 'interrupted'
    assert service.get(run_id)['summary']['total'] == 3


def test_lead_routes_and_payload_limits():
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    assert '/assets/workflow.js' in client.get('/').text
    assert '/assets/leads.js' in client.get('/leads').text
    assert '/assets/app.js' in client.get('/posting').text
    assert len(client.get('/api/leads/registries').json()) == 5
    assert client.post('/api/leads/filter', json=ROWS).json()['summary']['total'] == 3
    assert client.post('/api/leads/collect', json={'post_url': 'https://evil.test/posts/1'}).status_code == 400
    assert client.post('/api/leads/filter', content=b' ' * (5*1024*1024+1)).status_code == 413
    assert TestClient(server.app).post('/api/leads/collect', json={'post_url': URL}).status_code == 403


def test_history_never_overwrites_a_run_completed_after_first_read(tmp_path, monkeypatch):
    service, run_id = completed_service(tmp_path)
    actual_get = service.get
    calls = []
    def racing_read(value):
        saved = actual_get(value)
        calls.append(value)
        if len(calls) == 1:
            saved['status'] = 'running'
        return saved
    monkeypatch.setattr(service, 'get', racing_read)
    assert service.list_runs()[0]['status'] == 'partial'
    assert actual_get(run_id)['status'] == 'partial'


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def facebook_html():
    return '''<!doctype html><meta charset="utf-8"><nav role="navigation">Profile</nav>
      <div role="article"><p dir="auto">Main post is not a comment: Cần mua 0999999999</p><a href="/groups/test/posts/123">Post</a>
        <div role="article"><a href="/alice"><span dir="auto">Alice</span></a><div dir="auto">Cần mua 0912345678</div>
          <a href="/groups/test/posts/123?comment_id=c1">1 h</a>
          <div role="article"><a href="/bob">Bob</a><div dir="auto">xin giá</div><a href="/groups/test/posts/123?comment_id=c1&reply_comment_id=c2">1 h</a></div></div>
        <div role="article" style="display:none"><a href="/hidden">Hidden</a><div dir="auto">ẩn</div><a href="/groups/test/posts/123?comment_id=hidden">1 h</a></div>
      </div>
      <div role="article"><a href="/other">Other</a><div dir="auto">Recommended post comment</div><a href="/groups/test/posts/999?comment_id=c3">1 h</a></div>
      <button onclick="window.badClick=1">Like</button><button onclick="window.badClick=1">Reply</button><button onclick="window.badClick=1">Post</button>'''


@pytest.mark.browser
@pytest.mark.parametrize('timeout,elapsed,expected_count', [(300, 40, 2), (1, 1, 0)])
def test_collector_deadline_includes_navigation_and_preserves_results(browser, monkeypatch, tmp_path, timeout, elapsed, expected_count):
    context = browser.new_context()
    context.add_cookies([{'name': 'c_user', 'value': 'fixture', 'domain': '.facebook.com', 'path': '/'}])
    context.route('**/*', lambda route: route.fulfill(content_type='text/html', body=facebook_html()))
    from services import facebook_comment_collector as module
    clock = [0.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(module, 'sync_playwright', lambda: nullcontext(Mock()))
    monkeypatch.setattr(module, 'launch_context', lambda *args: context)
    page = context.new_page()
    original_goto = page.goto
    def goto(url, **kwargs):
        assert kwargs['timeout'] <= min(timeout * 1000, 45000)
        original_goto(url, **kwargs)
        clock[0] += elapsed
    monkeypatch.setattr(page, 'goto', goto)
    monkeypatch.setattr(page, 'wait_for_timeout', lambda ms: clock.__setitem__(0, clock[0] + ms / 1000))
    monkeypatch.setattr(context, 'new_page', lambda: page)
    def progress(rows):
        clock[0] = timeout
    status, rows, message = FacebookCommentCollector(tmp_path/'profile', timeout_seconds=timeout).collect(
        URL, 20, threading.Event(), progress)
    assert status == 'partial' and len(rows) == expected_count
    assert 'hết thời gian' in message
    if timeout == 300:
        assert '5 phút' in message


def test_collection_defaults_to_five_minutes_without_a_thirty_round_cutoff(tmp_path):
    collector = FacebookCommentCollector(tmp_path/'profile')
    assert collector.timeout_seconds == 300 and collector.max_rounds is None
    assert FacebookCommentCollector(tmp_path/'profile', timeout_seconds=900).timeout_seconds == 300


@pytest.mark.browser
@pytest.mark.parametrize('resolution', ['redirect', 'canonical', 'og', 'delayed', 'unresolved', 'ambiguous', 'external', 'checkpoint'])
def test_share_collection_resolves_original_post_only(browser, monkeypatch, tmp_path, resolution):
    share = 'https://www.facebook.com/share/p/AbC123'
    context = browser.new_context()
    context.add_cookies([{'name': 'c_user', 'value': 'fixture', 'domain': '.facebook.com', 'path': '/'}])
    html = facebook_html()
    if resolution == 'canonical':
        html += f'<link rel="canonical" href="{URL}">'
    elif resolution == 'og':
        html += f'<meta property="og:url" content="{URL}">'
    elif resolution == 'delayed':
        html += f'<script>setTimeout(() => history.replaceState(null, "", "{URL}"), 2400)</script>'
    elif resolution == 'ambiguous':
        html += f'<link rel="canonical" href="{URL}"><meta property="og:url" content="https://www.facebook.com/other/posts/999">'
    elif resolution == 'external':
        html += '<link rel="canonical" href="https://evil.test/other/posts/123">'
    elif resolution == 'checkpoint':
        html = '<input name="email"><input name="pass">'
    def route_page(route):
        if resolution == 'redirect' and '/share/' in route.request.url:
            # A new client navigation is intercepted too; Playwright routing
            # may bypass interception for HTTP redirect chains.
            route.fulfill(content_type='text/html', body=f'<script>location.replace("{URL}")</script>')
        else:
            route.fulfill(content_type='text/html', body=html)
    context.route('**/*', route_page)
    from services import facebook_comment_collector as module
    monkeypatch.setattr(module, 'sync_playwright', lambda: nullcontext(Mock()))
    monkeypatch.setattr(module, 'launch_context', lambda *args: context)
    status, rows, message = FacebookCommentCollector(tmp_path / 'profile', max_rounds=2).collect(
        share, 20, threading.Event(), lambda rows: None)
    if resolution in ('unresolved', 'ambiguous', 'external', 'checkpoint'):
        assert status == 'action_required' and not rows
    else:
        assert status == 'partial' and {row['id'] for row in rows} == {'c1', 'c2'}
        assert all(row['source_url'] == URL for row in rows)


@pytest.mark.browser
@pytest.mark.parametrize('checkpoint', [False, True])
def test_real_collector_reads_only_target_comments(browser, monkeypatch, tmp_path, checkpoint):
    context = browser.new_context()
    context.add_cookies([{'name': 'c_user', 'value': 'fixture', 'domain': '.facebook.com', 'path': '/'}])
    context.route('**/*', lambda route: route.fulfill(content_type='text/html', body=(
        '<input name="email"><input name="pass">' if checkpoint else facebook_html())))
    from services import facebook_comment_collector as module
    monkeypatch.setattr(module, 'sync_playwright', lambda: nullcontext(Mock()))
    monkeypatch.setattr(module, 'launch_context', lambda *args: context)
    snapshots = []
    collector = FacebookCommentCollector(tmp_path / 'profile', timeout_seconds=10, max_rounds=2)
    status, rows, message = collector.collect(URL, 20, threading.Event(), snapshots.append)
    if checkpoint:
        assert status == 'action_required' and not rows
    else:
        assert status == 'partial'
        assert len(rows) == 2 and {r['id'] for r in rows} == {'c1', 'c2'}
        assert rows[0]['raw_content'] == 'Cần mua 0912345678'
        assert rows[0]['fb_user_name'] == 'Alice'
        assert len(snapshots) == 2  # Repeated DOM snapshots do not duplicate comments.


@pytest.mark.browser
def test_collector_expands_text_before_applying_limit(browser, monkeypatch, tmp_path):
    context = browser.new_context()
    context.add_cookies([{'name': 'c_user', 'value': 'fixture', 'domain': '.facebook.com', 'path': '/'}])
    html = facebook_html().replace('Cần mua 0912345678</div>',
        'Cần mua 0912345678</div><button onclick="this.previousElementSibling.textContent += \' nhưng thôi không mua nữa\';this.remove()">See more</button>')
    context.route('**/*', lambda route: route.fulfill(content_type='text/html', body=html))
    from services import facebook_comment_collector as module
    monkeypatch.setattr(module, 'sync_playwright', lambda: nullcontext(Mock()))
    monkeypatch.setattr(module, 'launch_context', lambda *args: context)
    _, rows, _ = FacebookCommentCollector(tmp_path/'profile', max_rounds=1).collect(URL, 1, threading.Event(), lambda rows: None)
    assert len(rows) == 1 and 'thôi không mua nữa' in rows[0]['raw_content']
    assert not rows[0]['text_truncated']
    assert filter_records(rows)['records'][0]['classification'] == 'IGNORE'


@pytest.mark.browser
def test_lead_dashboard_collection_history_registry_and_download(browser, monkeypatch, tmp_path):
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', FixtureCollector())
    monkeypatch.setattr(server, 'lead_service', service)
    client = TestClient(server.app, base_url='http://localhost:8000')
    context = browser.new_context()
    failures, errors = [], []
    def route_api(route):
        req = route.request
        assert req.url.startswith('http://localhost:8000/'), req.url
        response = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
        if response.status_code >= 400: failures.append((req.url, response.status_code))
        route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
    context.route('**/*', route_api)
    page = context.new_page()
    page.on('pageerror', lambda err: errors.append(str(err)))
    page.goto('http://localhost:8000/leads')
    assert not page.locator('#extra-tools').evaluate('e => e.open')
    page.locator('#extra-tools > summary').click()
    page.locator('#external-post > summary').click()
    page.locator('#post-url').fill(URL)
    page.locator('#collect').click()
    page.wait_for_function("document.getElementById('total').innerText === '3'")
    page.wait_for_function("!document.getElementById('collect').disabled")
    assert page.locator('#registries > details').count() == 5
    assert page.evaluate('window.injected') is None
    assert '<img' in page.locator('#results').inner_text()
    assert 'contacts:' not in page.locator('#results').inner_text()
    page.locator('#classification').select_option('LEAD_POTENTIAL')
    assert page.locator('#results tr:not(.post-heading)').count() == 1
    with page.expect_download() as download:
        page.locator('#export').click()
    assert download.value.suggested_filename == 'facebook_leads.xlsx'
    ws = openpyxl.load_workbook(BytesIO(download.value.path().read_bytes())).active
    assert ws.max_row == 2 and ws['E2'].value == '0912345678'
    page.reload()
    page.locator('#history-box > summary').click()
    page.locator('#history').select_option(service.list_runs()[0]['id'])
    page.wait_for_function("document.getElementById('total').innerText === '3'")
    assert not errors and not failures
    screenshot = Path(__file__).resolve().parents[1] / '.cache' / 'test-runs' / 'lead-dashboard.png'
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot), full_page=True)
    # Local sample path is a working fallback with no Facebook request.
    page.locator('#extra-tools > summary').click()
    page.locator('#manual-tools > summary').click()
    page.locator('#sample').click()
    page.wait_for_function("document.getElementById('notice').innerText.includes('dữ liệu mẫu')")
    context.close()
