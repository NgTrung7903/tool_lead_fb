from io import BytesIO

import openpyxl

from services.customer_records import aggregate_customers
from services.excel_exporter import export_records_to_excel, workbook_bytes
from services.lead_filter_service import filter_records


POST = 'https://www.facebook.com/groups/a/posts/123'
OTHER = 'https://www.facebook.com/groups/b/posts/456'


def rows():
    return filter_records([
        {'id': '1', 'author': 'Lan', 'fb_user_url': 'https://www.facebook.com/lan',
         'source_url': POST, 'text': 'xin giá', 'comment_url': POST + '?comment_id=1'},
        {'id': '2', 'author': 'Lan', 'fb_user_url': 'https://m.facebook.com/lan?__tn__=x',
         'source_url': POST, 'text': 'Cần mua 0912345678', 'comment_url': POST + '?comment_id=2'},
        {'id': '3', 'author': 'Lan', 'fb_user_url': 'https://www.facebook.com/lan',
         'source_url': OTHER, 'text': 'xin giá'},
    ])['records']


def test_one_customer_across_groups_preserves_comments_contacts_and_scores():
    original = rows()
    result = aggregate_customers(original)
    assert len(result) == 1
    customer = result[0]
    assert customer['comment_count'] == 3
    assert customer['group_count'] == 2
    assert {source['source_url'] for source in customer['sources']} == {POST, OTHER}
    assert [c['id'] for c in customer['comments']] == ['1', '2', '3']
    assert 'xin giá' in customer['raw_content'] and '0912345678' in customer['raw_content']
    assert customer['contacts']['primary_phone'] == '0912345678'
    assert customer['score'] == original[1]['score']
    assert aggregate_customers(result) == result
    assert 'comments' not in original[0]


def test_anonymous_unknown_and_distinct_profiles_are_not_merged():
    records = rows()[:1]
    base = records[0]
    for status in ('anonymous', 'unknown'):
        assert len(aggregate_customers([{**base, 'identity_status': status}] * 2)) == 2
    assert len(aggregate_customers([base, {**base, 'fb_user_url': 'https://www.facebook.com/another'}])) == 2


def test_excel_has_one_customer_row_with_all_source_groups():
    wb = openpyxl.load_workbook(BytesIO(workbook_bytes(export_records_to_excel, rows())))
    assert len(wb.worksheets) == 1
    ws = wb.active
    assert ws.max_row == 2
    assert ws['L2'].value.splitlines() == [POST, OTHER]
    assert ws['E2'].value == '0912345678'
    assert ws['W2'].value.splitlines() == [POST + '?comment_id=1', POST + '?comment_id=2']
    assert 'xin giá' in ws['K2'].value


def test_same_display_name_without_profile_is_not_merged_across_groups():
    records = [{**row, 'fb_user_url': None} for row in rows()]
    assert len(aggregate_customers(records)) == 2


def test_filter_matches_a_source_with_all_requested_scope_fields():
    from services.lead_filter_service import select_customer_records
    records = rows()
    records[0].update(campaign_id='first', posting_task_id='t1', group_name='Nhóm A')
    records[1].update(campaign_id='first', posting_task_id='t1', group_name='Nhóm A')
    records[2].update(campaign_id='second', posting_task_id='t2', group_name='Nhóm B')
    customers = aggregate_customers(records)
    selected = select_customer_records(customers, campaign_id='second', group_key='https://www.facebook.com/groups/b')
    assert len(selected) == 1 and selected[0]['comment_count'] == 3
    assert select_customer_records(customers, campaign_id='first', group_key='https://www.facebook.com/groups/b') == []
