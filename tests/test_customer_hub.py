"""Customer aggregation and exports use the same scope and latest comment text."""
from io import BytesIO
from unittest.mock import Mock

from fastapi.testclient import TestClient
import openpyxl

from api import server
from services.lead_filter_service import LeadFilterService
import pytest
from playwright.sync_api import sync_playwright


FIRST = 'https://www.facebook.com/groups/first/posts/123'
SECOND = 'https://www.facebook.com/groups/second/posts/456'


def seed(service, run_id, date, rows, campaign='campaign-a'):
    from services.lead_filter_service import filter_records
    run = {'id': run_id, 'created_at': date, 'finished_at': date, 'status': 'partial',
           'context': {'campaign_id': campaign}, 'post_url': FIRST,
           **filter_records(rows)}
    service._save(run)


def setup_hub(tmp_path, monkeypatch):
    service = LeadFilterService(tmp_path/'runs', tmp_path/'profile')
    first = {'id': 'same', 'source_url': FIRST, 'raw_content': 'xin giá',
             'fb_user_name': 'Alice', 'campaign_id': 'campaign-a', 'group_name': 'Nhóm A', 'posting_task_id': 'task-a'}
    second = {'id': 'same', 'source_url': SECOND, 'raw_content': 'Cần mua 0987654321',
              'fb_user_name': 'Bob', 'campaign_id': 'campaign-b', 'group_name': 'Nhóm B', 'posting_task_id': 'task-b'}
    seed(service, 'a'*32, '2026-10-01T00:00:00+00:00', [first, second])
    # A refresh from a pasted share link lacks campaign metadata. Keep its source association.
    edited = {k: v for k, v in first.items() if k not in ('campaign_id', 'group_name', 'posting_task_id')}
    edited['raw_content'] = 'Cần mua 0912345678'
    seed(service, 'b'*32, '2026-10-02T00:00:00+00:00', [edited], campaign=None)
    monkeypatch.setattr(server, 'lead_service', service)
    monkeypatch.setattr(server, 'campaign_service', Mock(list_campaigns=lambda: []))
    return service, TestClient(server.app, headers={'X-Revoland-Client': 'local'})


def test_latest_comment_is_unique_and_keeps_group_campaign_association(tmp_path, monkeypatch):
    service, client = setup_hub(tmp_path, monkeypatch)
    result = client.get('/api/leads/results').json()
    assert result['summary']['total'] == 2  # Same ID on different posts stays separate.
    alice = next(r for r in result['records'] if r['fb_user_name'] == 'Alice')
    assert alice['contacts']['primary_phone'] == '0912345678'
    assert alice['campaign_id'] == 'campaign-a' and alice['group_name'] == 'Nhóm A'
    assert alice['posting_task_id'] == 'task-a'
    assert alice['latest_run_id'] == 'b'*32
    assert service.get('a'*32)['records'][0]['raw_content'] == 'xin giá'


def test_saved_false_positive_is_reclassified_for_table_and_excel_without_rewriting_history(tmp_path, monkeypatch):
    service, client = setup_hub(tmp_path, monkeypatch)
    old = service.get('b'*32)
    old['records'][0].update(raw_content='xấu vcl nhìn k muốn mua', classification='LEAD_POTENTIAL',
                             score=40, registry_version='1.0.0')
    service._save(old)
    current = client.get('/api/leads/results', params={'posting_task_id': 'task-a'}).json()
    assert current['records'][0]['classification'] == 'IGNORE'
    assert current['records'][0]['score'] == 0
    snapshot = client.get('/api/leads/runs/' + 'b'*32).json()
    assert snapshot['records'][0]['classification'] == 'IGNORE'
    ws = openpyxl.load_workbook(BytesIO(client.get('/api/leads/runs/' + 'b'*32 + '/excel').content)).active
    assert ws['C2'].value == 'IGNORE' and ws['D2'].value == 0
    assert service.get('b'*32)['records'][0]['classification'] == 'LEAD_POTENTIAL'


@pytest.mark.parametrize('text,classification,score', [('xin hướng nhà', 'NEEDS_REVIEW', 25),
                                                     ('2 tỷ mua luôn', 'LEAD_POTENTIAL', 40)])
def test_saved_property_inquiries_are_reclassified_with_new_rules(tmp_path, monkeypatch, text, classification, score):
    service, client = setup_hub(tmp_path, monkeypatch)
    old = service.get('b'*32)
    old['records'][0].update(raw_content=text, classification='IGNORE', score=0, registry_version='1.0.1')
    service._save(old)
    rows = client.get('/api/leads/results', params={'posting_task_id': 'task-a'}).json()['records']
    assert rows[0]['classification'] == classification and rows[0]['score'] == score
    assert not rows[0]['contacts']['primary_phone']
    ws = openpyxl.load_workbook(BytesIO(client.get('/api/leads/runs/' + 'b'*32 + '/excel').content)).active
    assert ws['C2'].value == classification and ws['D2'].value == score
    assert service.get('b'*32)['records'][0]['classification'] == 'IGNORE'


def test_customer_export_matches_all_filters_including_search(tmp_path, monkeypatch):
    _, client = setup_hub(tmp_path, monkeypatch)
    params = {'campaign_id': 'campaign-a', 'group_key': 'https://www.facebook.com/groups/first',
              'classification': 'LEAD_POTENTIAL', 'q': '091234', 'posting_task_id': 'task-a'}
    result = client.get('/api/leads/results', params=params).json()
    assert result['summary']['total'] == 1
    response = client.get('/api/leads/results/excel', params=params)
    ws = openpyxl.load_workbook(BytesIO(response.content)).active
    assert ws.max_row == 2 and ws['E2'].value == '0912345678'
    assert ws['S2'].value == 'campaign-a' and ws['U2'].value == 'Nhóm A'
    params['q'] = 'Bob'
    assert client.get('/api/leads/results', params=params).json()['records'] == []
    assert openpyxl.load_workbook(BytesIO(client.get('/api/leads/results/excel', params=params).content)).active.max_row == 1
    assert client.get('/api/leads/results', params={'classification': 'bad'}).status_code == 400
    assert client.get('/api/leads/results', params={'interest_level': 'bad'}).status_code == 400
    assert client.get('/api/leads/results', params={'interest_level':'weak'}).json()['records'] == []
    strong = client.get('/api/leads/results', params={'interest_level':'strong'}).json()
    assert strong['summary']['total'] == 2
    wb = openpyxl.load_workbook(BytesIO(client.get('/api/leads/results/excel', params={'interest_level':'strong'}).content))
    assert len(wb.worksheets) == 1
    assert wb.active.max_row == 3 and wb.active['X2'].value == 'Mạnh'


def test_same_customer_in_multiple_groups_is_one_row_and_filters_keep_all_sources(tmp_path, monkeypatch):
    service, client = setup_hub(tmp_path, monkeypatch)
    latest = service.get('b'*32)
    latest['records'][0]['fb_user_url'] = 'https://www.facebook.com/profile.php?id=123'
    service._save(latest)
    seed(service, 'c'*32, '2026-10-03T00:00:00+00:00', [{
        'id': 'second-comment', 'source_url': SECOND, 'fb_user_name': 'Alice',
        'fb_user_url': 'https://www.facebook.com/groups/second/user/123/',
        'text': 'chot gia 2 ty', 'group_name': 'Nhóm B',
        'campaign_id': 'campaign-b', 'posting_task_id': 'task-b',
    }], campaign='campaign-b')
    params = {'q': 'Alice', 'campaign_id': 'campaign-b', 'group_key': 'https://www.facebook.com/groups/second'}
    result = client.get('/api/leads/results', params=params).json()
    assert result['summary']['total'] == 1
    customer = result['records'][0]
    assert customer['comment_count'] == 2 and customer['group_count'] == 2
    assert {source['source_url'] for source in customer['sources']} == {FIRST, SECOND}
    assert customer['contacts']['primary_phone'] == '0912345678'
    assert {group['key'] for group in result['groups']} == {'https://www.facebook.com/groups/first', 'https://www.facebook.com/groups/second'}
    wb = openpyxl.load_workbook(BytesIO(client.get('/api/leads/results/excel', params=params).content))
    assert len(wb.worksheets) == 1 and wb.active.max_row == 2
    assert set(wb.active['L2'].value.splitlines()) == {FIRST, SECOND}
    assert set(wb.active['U2'].value.splitlines()) == {'Nhóm A', 'Nhóm B'}


@pytest.mark.browser
def test_customer_hub_group_campaign_search_and_excel_in_browser(tmp_path, monkeypatch):
    service, client = setup_hub(tmp_path, monkeypatch)
    saved = service.get('b'*32)
    saved['records'][0]['fb_user_url'] = 'https://www.facebook.com/alice'
    from services.lead_filter_service import filter_records
    saved['records'].extend(filter_records([{
        'id': 'another', 'source_url': FIRST, 'fb_user_name': 'Alice',
        'raw_content': 'Cho mình xem nhà cuối tuần. ' + 'Mình muốn được tư vấn chi tiết về căn nhà. ' * 20,
        'campaign_id': 'campaign-a',
        'posting_task_id': 'task-a', 'group_name': 'Nhóm A',
        'fb_user_url': 'https://www.facebook.com/alice',
    }, {
        'id': 'another-group', 'source_url': SECOND, 'fb_user_name': 'Alice',
        'raw_content': 'chot gia 2 ty', 'campaign_id': 'campaign-b',
        'posting_task_id': 'task-b', 'group_name': 'Nhóm B',
        'fb_user_url': 'https://m.facebook.com/alice?tracking=1',
    }])['records'])
    service._save(saved)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        errors = []
        def serve(route):
            req = route.request
            assert req.url.startswith('http://localhost:8000/')
            response = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
        context.route('**/*', serve)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://localhost:8000/leads')
        page.wait_for_function("document.getElementById('total').innerText === '2'")
        assert not page.locator('#extra-tools').evaluate('e => e.open')
        assert page.locator('#results tr:not(.post-heading)').count() == 2
        assert page.locator('#results .post-heading').count() == 0
        assert '3 bình luận' in page.locator('#results').inner_text()
        assert '2 nhóm' in page.locator('#results').inner_text()
        assert 'Cho mình xem nhà cuối tuần' in page.locator('#results').inner_text()
        assert page.get_by_role('columnheader', name='Nhóm', exact=True).count() == 1
        alice = page.locator('#results > tr').filter(has=page.get_by_text('Alice', exact=True))
        assert alice.count() == 1
        group_sections = alice.locator('.customer-comment-group')
        assert group_sections.count() == 2
        first_group = group_sections.filter(has=page.get_by_text('Nhóm A', exact=True))
        second_group = group_sections.filter(has=page.get_by_text('Nhóm B', exact=True))
        assert 'Cho mình xem nhà cuối tuần' in first_group.inner_text()
        assert 'chot gia 2 ty' in second_group.inner_text()
        assert first_group.get_by_text('Nhóm A', exact=True).evaluate(
            "name => getComputedStyle(name).textDecorationLine"
        ) == 'none'
        page.locator('#campaign-filter').select_option('campaign-a')
        page.locator('#group-filter').select_option('https://www.facebook.com/groups/first')
        page.locator('#classification').select_option('LEAD_POTENTIAL')
        page.locator('#search').fill('Bob')
        assert page.locator('#export').is_disabled()
        page.locator('#search').fill('091234')
        assert page.locator('#results tr:not(.post-heading)').count() == 1
        assert 'Alice' in page.locator('#results').inner_text()
        preview = page.locator('#results td').nth(2).locator('.customer-preview')
        toggle = page.get_by_role('button', name='Xem đầy đủ bình luận', exact=True)
        toggle.wait_for(state='visible')
        assert preview.evaluate('e => e.clientHeight <= 240 && e.scrollHeight > e.clientHeight')
        toggle.click()
        assert page.get_by_role('button', name='Thu gọn', exact=True).get_attribute('aria-expanded') == 'true'
        assert preview.evaluate('e => e.clientHeight >= e.scrollHeight')
        page.locator('#refresh-results').click()
        page.wait_for_function("document.querySelector('#results .customer-preview-toggle')?.getAttribute('aria-expanded') === 'true'")
        page.get_by_role('button', name='Thu gọn', exact=True).click()
        assert page.get_by_role('button', name='Xem đầy đủ bình luận', exact=True).get_attribute('aria-expanded') == 'false'
        with page.expect_download() as download:
            page.locator('#export').click()
        ws = openpyxl.load_workbook(BytesIO(download.value.path().read_bytes())).active
        assert ws.max_row == 2 and ws['E2'].value == '0912345678'
        assert service.list_runs()[0]['id'] == 'b'*32  # Viewing/exporting never collects.
        assert not errors
        from pathlib import Path
        screenshot = Path(__file__).resolve().parents[1] / '.cache' / 'test-runs' / 'customer-preview.png'
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        context.close()
        browser.close()
