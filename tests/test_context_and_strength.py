from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import openpyxl
import pytest
from playwright.sync_api import sync_playwright

from core.filter_engine import RegistryFilterEngine
from services.lead_filter_service import LeadFilterService, filter_records
from services.excel_exporter import export_records_to_excel, workbook_bytes
from services.facebook_comment_collector import FacebookCommentCollector


@pytest.mark.parametrize('text,category,level', [
    ('dm', 'NEEDS_REVIEW', 'unclear'), ('DM me the price', 'NEEDS_REVIEW', 'moderate'),
    ('please DM me details', 'NEEDS_REVIEW', 'moderate'), ('dm cho mình thông tin', 'NEEDS_REVIEW', 'moderate'),
    ("I'm interested in buying, DM me", 'LEAD_POTENTIAL', 'strong'),
    ('dm giá cao thế', 'IGNORE', 'none'), ('dm đẹp quá, 2 tỷ mua luôn', 'LEAD_POTENTIAL', 'strong'),
    ("don't DM me", 'IGNORE', 'none'), ('đừng DM tôi', 'IGNORE', 'none'),
    ('do not direct message me', 'IGNORE', 'none'), ('đừng nhắn cho mình', 'IGNORE', 'none'),
    ("I don't want to buy", 'IGNORE', 'none'), ('not interested in buying', 'IGNORE', 'none'),
    ('muốn mua nhưng đừng DM tôi', 'NEEDS_REVIEW', 'unclear'),
    ('xin hướng nhà', 'NEEDS_REVIEW', 'moderate'), ('2 tỷ mua luôn', 'LEAD_POTENTIAL', 'strong'),
    ('ib', 'NEEDS_REVIEW', 'weak'), ('đẹp quá', 'IGNORE', 'weak'),
    ('xấu vcl nhìn k muốn mua', 'IGNORE', 'none'),
])
def test_context_and_strength(text, category, level):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == category, result
    assert result['interest_level'] == level, result
    if level in ('strong', 'moderate', 'weak'):
        assert result['interest_evidence']


@pytest.mark.parametrize('text', [
    'mua', 'MUA', 'chot gia 2 ty', '2 ty chot gia', '2,5 ty chot gia',
    'can mua', 'muon mua', 'mua can nay', 'cho minh dat coc',
])
def test_unaccented_purchase_comments(text):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == 'LEAD_POTENTIAL', result
    assert result['interest_level'] == 'strong'
    assert 'direct_purchase' in result['signals']['intents']


@pytest.mark.parametrize('text', [
    'del mua', 'dell mua', 'đéo mua', 'deo mua', 'dech mua', 'khong mua',
    'khong muon mua', 'ko mua', 'chua mua', 'khong chot gia 2 ty',
    'chua chot gia', 'tien dau ma mua', 'asdkfa', 'huhuh qua dat',
])
def test_unaccented_refusals_and_unrelated_text_are_not_purchase_leads(text):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == 'IGNORE', result
    assert result['interest_level'] == 'none'


@pytest.mark.parametrize('accented,plain', [
    ('chốt giá 2 tỷ', 'chot gia 2 ty'),
    ('xin hướng nhà', 'xin huong nha'),
    ('không muốn mua', 'khong muon mua'),
    ('nhắn cho mình', 'nhan cho minh'),
    ('đừng nhắn cho mình', 'dung nhan cho minh'),
    ('nhà có dính quy hoạch không?', 'nha co dinh quy hoach khong?'),
])
def test_accented_and_unaccented_rules_have_same_assessment(accented, plain):
    engine = RegistryFilterEngine()
    first, second = engine.evaluate(accented), engine.evaluate(plain)
    for key in ('classification', 'score', 'interest_level'):
        assert first[key] == second[key], (first, second)


def test_saved_unaccented_comment_is_reclassified_without_rewriting_history(tmp_path):
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile')
    row = filter_records([{'id': 'c1', 'author': 'Khách A', 'text': '2 ty chot gia'}])['records'][0]
    row.update(registry_version='1.3.0', classification='IGNORE', score=0, interest_level='none')
    run_id = 'a' * 32
    service._save({'id': run_id, 'records': [row], 'status': 'partial'})
    displayed = service.get_for_display(run_id)['records'][0]
    assert displayed['classification'] == 'LEAD_POTENTIAL'
    assert displayed['registry_version'] == '1.4.0'
    assert service.get(run_id)['records'][0]['classification'] == 'IGNORE'


def test_anonymous_interest_and_contact_are_independent():
    rows = filter_records([
        {'id':'a', 'author':'Anonymous participant', 'text':'2 tỷ mua luôn',
         'comment_url':'https://www.facebook.com/groups/test/posts/123?comment_id=a',
         'fb_user_url':'https://www.facebook.com/fake-user'},
        {'id':'b', 'author':'Người tham gia ẩn danh', 'text':'Cần mua 0912345678'},
        {'id':'c', 'author':'Chưa xác định tác giả', 'text':'xin hướng nhà'},
    ])['records']
    assert rows[0]['classification'] == 'LEAD_POTENTIAL' and rows[0]['identity_status'] == 'anonymous'
    assert rows[0]['fb_user_url'] is None and rows[0]['contact_channels'] == ['comment']
    assert rows[1]['contact_channels'] == ['phone'] and rows[1]['identity_status'] == 'anonymous'
    assert rows[2]['identity_status'] == 'unknown' and rows[2]['contact_channels'] == []
    ws = openpyxl.load_workbook(BytesIO(workbook_bytes(export_records_to_excel, rows))).active
    assert ws['X2'].value == 'Mạnh' and ws['Z2'].value == 'Ẩn danh'
    assert ws['AA2'].value == 'Có link comment'


def test_truncated_purchase_text_has_unclear_strength():
    row = filter_records([{'text':'2 tỷ mua luôn', 'text_truncated':True}])['records'][0]
    assert row['classification'] == 'NEEDS_REVIEW' and row['interest_level'] == 'unclear'


@pytest.mark.browser
def test_collector_retains_anonymous_and_unknown_authors_without_profile_links(tmp_path, monkeypatch):
    from services import facebook_comment_collector as module
    url = 'https://www.facebook.com/groups/test/posts/123'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies([{'name':'c_user','value':'fixture','domain':'.facebook.com','path':'/'}])
        html = '<meta charset="utf-8"><nav role="navigation">Account</nav>'
        for cid, author in [('a','Anonymous participant'), ('b','Người tham gia ẩn danh'), ('c','')]:
            html += f'<div role="article"><span dir="auto">{author}</span><div dir="auto">2 tỷ mua luôn</div><a href="{url}?comment_id={cid}">1 h</a></div>'
        context.route('**/*', lambda route: route.fulfill(content_type='text/html', body=html))
        monkeypatch.setattr(module, 'sync_playwright', lambda: nullcontext(Mock()))
        monkeypatch.setattr(module, 'launch_context', lambda *args: context)
        import threading
        _, rows, _ = FacebookCommentCollector(tmp_path/'profile', max_rounds=1).collect(url, 10, threading.Event(), lambda rows: None)
        assert len(rows) == 3
        assert [r['identity_status'] for r in rows] == ['anonymous', 'anonymous', 'unknown']
        assert all(not r['fb_user_url'] for r in rows)
        assert all(r['raw_content'] == '2 tỷ mua luôn' for r in rows)
        browser.close()


def test_anonymous_comments_with_same_name_are_not_merged_as_one_person(tmp_path):
    class Collector:
        def collect(self, url, limit, stop, progress):
            rows = [{'id': cid, 'source_url': url, 'author':'Anonymous participant',
                     'raw_content':'2 tỷ mua luôn', 'fb_user_name':'Anonymous participant'} for cid in ('a','b')]
            progress(rows)
            return 'partial', rows, 'fixture'
    service = LeadFilterService(tmp_path/'runs', tmp_path/'profile', Collector())
    for _ in range(2):
        run = service.start('https://www.facebook.com/groups/test/posts/123')
        service._thread.join(5)
        assert service.get_for_display(run['id'])['summary']['total'] == 2
