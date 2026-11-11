from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import openpyxl
import pytest
from fastapi.testclient import TestClient

from api import server
from models.schema import GroupPostStatusEnum as S, GroupTaskResult, PostingCampaign
from services.excel_exporter import export_records_to_excel, export_campaigns_to_excel, workbook_bytes
from services.report_service import (COMMENT_EXAMPLE, MAX_IMPORT_BYTES, campaign_report_bytes,
    comment_report_bytes, parse_comment_records, prepare_comment_report)


def sheet(content):
    return openpyxl.load_workbook(BytesIO(content)).active


def campaign():
    return PostingCampaign(id='campaign_test',listing_id='listing_test',listing_title='Căn thử nghiệm',
        formatted_content='Content',source_mode='live',total_groups=2,tasks=[
            GroupTaskResult(task_id='t1',group_id='g1',group_name='Nhóm A',group_url='https://www.facebook.com/groups/a',
                status=S.POSTED,post_url='https://www.facebook.com/groups/a/posts/123',retry_count=1,
                evidence='customer_confirmed:posted',submission_started=True),
            GroupTaskResult(task_id='t2',group_id='g2',group_name='Nhóm B',group_url='https://www.facebook.com/groups/b',
                status=S.UNKNOWN,error_message='Chưa xác nhận',submission_started=True)])


def test_campaign_excel_keeps_uncertainty_and_group_results():
    ws = sheet(workbook_bytes(export_campaigns_to_excel,[campaign()]))
    assert ws.max_row == 3
    assert ws['J2'].value == 'posted' and ws['J3'].value == 'unknown'
    assert ws['K2'].value.endswith('/posts/123') and ws['K3'].value is None
    assert ws['L3'].value == 'Chưa xác nhận' and ws['M2'].value == 1
    assert ws.freeze_panes == 'A2' and ws.auto_filter.ref == 'A1:T3'
    assert ws['R2'].value == 'unchecked'


def test_comments_excel_preserves_phone_and_does_not_claim_lead_created():
    content = comment_report_bytes([{'id':'c1','author':'Khách','text':'Cần mua 0912345678','listing_id':'L'}])
    ws = sheet(content)
    assert ws['E2'].value == '0912345678' and ws['E2'].data_type == 's'
    assert ws['C2'].value == 'LEAD_POTENTIAL'
    assert ws['N2'].value == 'Lead tiềm năng'
    assert ws['O2'].value == 'L' and ws['Q2'].value == 'not_synced'


def test_imported_sync_status_is_explicit_and_keeps_lead_id():
    ws = sheet(comment_report_bytes([{'text':'Cần mua căn này','customer_name':'Khách',
        'sync_status':'synced','revoland_lead_id':'REV_1'}]))
    assert ws['N2'].value == 'Đã đồng bộ theo bản ghi'
    assert ws['P2'].value == 'REV_1'
    assert 'Theo Dữ Liệu Nhập' in ws['Q1'].value


def test_lead_without_comment_preserves_contacts_and_sync_state():
    ws = sheet(comment_report_bytes([{'customer_name':'Lead nhập','phone_number':'0912.345.678',
        'email':'sample@example.com','sync_status':'failed','intent_summary':'Khách muốn xem nhà','listing_id':'L1'}]))
    assert ws['E2'].value == '0912345678'
    assert ws['H2'].value == 'sample@example.com'
    assert ws['N2'].value == 'Đồng bộ thất bại'
    assert ws['K2'].value is None
    assert ws['R2'].value == 'lead'


def test_exported_user_text_cannot_become_formula():
    ws = sheet(comment_report_bytes([{'author':'=HYPERLINK("https://example.com")','text':'=1+1\u0001'}]))
    assert ws['F2'].value.startswith('=HYPERLINK') and ws['F2'].data_type == 's'
    assert ws['K2'].value == '=1+1' and ws['K2'].data_type == 's'
    post = campaign();post.listing_title='=1+1'
    assert sheet(workbook_bytes(export_campaigns_to_excel,[post]))['C2'].data_type == 's'


@pytest.mark.parametrize('payload',[COMMENT_EXAMPLE,{'records':COMMENT_EXAMPLE},{'comments':COMMENT_EXAMPLE}])
def test_comment_import_supported_shapes(payload):
    assert len(parse_comment_records(payload)) == 2


@pytest.mark.parametrize('payload',[{},None,[{'text':' '}],[{'author':'No content'}],[{'text':'a'*20001}]])
def test_invalid_comment_import_is_rejected(payload):
    with pytest.raises(ValueError): parse_comment_records(payload)


def test_too_many_records_rejected():
    with pytest.raises(ValueError,match='5.000'):parse_comment_records([{'text':'a'}]*5001)


def test_empty_reports_have_headers():
    assert sheet(comment_report_bytes([])).max_row == 1
    assert sheet(workbook_bytes(export_campaigns_to_excel,[])).max_row == 1


def test_legacy_export_function_can_write_path(tmp_path):
    path=tmp_path/'nested'/'report.xlsx'
    export_records_to_excel(prepare_comment_report(parse_comment_records(COMMENT_EXAMPLE)),path)
    assert openpyxl.load_workbook(path).active.max_row == 3


def test_export_api_downloads_and_campaign_filter(monkeypatch):
    svc=Mock();svc.list_campaigns.return_value=[campaign()];svc.get_campaign.return_value=campaign()
    monkeypatch.setattr(server,'campaign_service',svc)
    client=TestClient(server.app,headers={'X-Revoland-Client':'local'})
    response=client.get('/api/exports/campaigns?campaign_id=campaign_test')
    assert response.status_code == 200 and response.content.startswith(b'PK')
    assert 'attachment' in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    assert sheet(response.content).max_row == 3
    svc.list_campaigns.assert_not_called()
    assert client.get('/api/exports/campaigns').status_code == 200
    svc.get_campaign.return_value=None
    assert client.get('/api/exports/campaigns?campaign_id=missing').status_code == 404
    sample=client.get('/api/exports/comments/example')
    assert sample.status_code == 200 and isinstance(sample.json(),list)
    exported=client.post('/api/exports/comments',json=sample.json())
    assert exported.status_code == 200 and sheet(exported.content).max_row == 3


def test_comment_export_api_validation_and_size_limit():
    client=TestClient(server.app,headers={'X-Revoland-Client':'local'})
    assert client.post('/api/exports/comments',json=[{'author':'Missing text'}]).status_code == 400
    assert client.post('/api/exports/comments',content=b' '* (MAX_IMPORT_BYTES+1),
        headers={'Content-Type':'application/json'}).status_code == 413
    raw=TestClient(server.app)
    assert raw.post('/api/exports/comments',json=COMMENT_EXAMPLE).status_code == 403


def test_cli_exports_comments_and_posting_history(tmp_path):
    root=Path(__file__).resolve().parent.parent
    input_file=tmp_path/'comments.json';input_file.write_text(json.dumps(COMMENT_EXAMPLE),encoding='utf-8')
    env={**os.environ,'REVOLAND_DATA_DIR':str(tmp_path/'runtime')}
    comments=tmp_path/'comments.xlsx'
    first=subprocess.run([sys.executable,str(root/'cli.py'),'--export-comments',str(input_file),'--output',str(comments)],
        cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert first.returncode == 0,first.stderr
    assert openpyxl.load_workbook(comments).active.max_row == 3
    posting=tmp_path/'posting.xlsx'
    second=subprocess.run([sys.executable,str(root/'cli.py'),'--export-posts','--output',str(posting)],
        cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert second.returncode == 0,second.stderr
    assert openpyxl.load_workbook(posting).active.max_row == 1
    repeated=subprocess.run([sys.executable,str(root/'cli.py'),'--export-posts','--output',str(posting)],
        cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert repeated.returncode != 0 and 'đã tồn tại' in repeated.stderr


def test_cli_export_does_not_recover_or_rewrite_running_campaign(tmp_path):
    from services.campaign_service import CampaignService
    root=Path(__file__).resolve().parent.parent
    runtime=tmp_path/'runtime'
    service=CampaignService(Mock(),Mock(),Mock(),runtime/'data'/'campaigns.sqlite3')
    saved=campaign();saved.status='running';saved.tasks[1].status=S.RUNNING
    service._save(saved)
    output=tmp_path/'running.xlsx'
    result=subprocess.run([sys.executable,str(root/'cli.py'),'--export-posts','--output',str(output)],
        cwd=root,env={**os.environ,'REVOLAND_DATA_DIR':str(runtime)},capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode == 0,result.stderr
    assert service.get_campaign(saved.id).model_dump() == saved.model_dump()
    assert openpyxl.load_workbook(output).active['J3'].value == 'running'
