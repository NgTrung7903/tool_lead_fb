"""Smoke-test the actual EXE in an isolated runtime, without real accounts/APIs."""
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import openpyxl
import requests


def stop_process_tree(process):
    if process.poll() is None:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW)
        process.wait(timeout=20)


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    latest = root / 'dist' / 'revoland-link-v18' / 'CongCuBDS_JSON.exe'
    executable = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else latest
    runtime = root / '.cache' / 'test-runs' / ('exe-verification-' + uuid.uuid4().hex)
    runtime.mkdir(parents=True)
    environment = dict(os.environ)
    for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','OPENAI_API_KEY'):
        environment.pop(key, None)
    system_root = environment.get('SystemRoot', r'C:\Windows')
    environment['PATH'] = system_root + r'\System32;' + system_root
    environment['REVOLAND_DATA_DIR'] = str(runtime / 'customer')
    environment['PLAYWRIGHT_BROWSERS_PATH'] = str(runtime / 'intentionally-missing-browser-cache')
    result_path = runtime / 'self-test.json'
    checked = subprocess.run([str(executable),'--self-test',str(result_path)],
        cwd=runtime, env=environment, capture_output=True, text=True, encoding='utf-8',
        timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    if checked.returncode != 0:
        raise RuntimeError('EXE self-test failed:\n' + checked.stdout + '\n' + checked.stderr)
    report = {'self_test':json.loads(result_path.read_text(encoding='utf-8'))}
    assert report['self_test']['passed'] and report['self_test']['frozen']
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port = listener.getsockname()[1]
    log_path = runtime / 'server.log'
    with log_path.open('w',encoding='utf-8') as log:
        process = subprocess.Popen([str(executable),'--no-browser','--port',str(port)],
            cwd=runtime, env=environment, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            url = f'http://127.0.0.1:{port}'
            session = requests.Session()
            session.trust_env = False
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('EXE server exited:\n' + log_path.read_text(encoding='utf-8'))
                try:
                    response = session.get(url,timeout=2)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError('EXE server startup timed out:\n' + log_path.read_text(encoding='utf-8'))
            report['dashboard'] = '/assets/workflow.js' in response.text and '/assets/common.js' in response.text
            from build_info import BUILD_ID, BUILD_NAME
            report['release_identity'] = session.get(url+'/api/app-info',timeout=10).json()['build_id'] == BUILD_ID
            report['release_label'] = ('id="build-label">' + BUILD_NAME) in response.text
            report['primary_link_input'] = 'Lấy tin &amp; soạn nội dung' in response.text or 'Lấy tin & soạn nội dung' in response.text
            reopened = subprocess.run([str(executable), '--no-browser'], cwd=runtime,
                env=environment, capture_output=True, text=True, encoding='utf-8',
                timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
            report['same_build_reopen'] = reopened.returncode == 0 and 'Tool đang chạy sẵn' in reopened.stdout
            report['removed_tools_absent'] = all(marker not in response.text for marker in
                ('id="rewrite"', 'id="rewrite-comparison"', 'id="text-form"', 'id="folder-form"'))
            report['posting_queue_hint'] = 'đăng lần lượt từng nhóm' in response.text and '100 nhóm' in response.text
            report['posting_delay_warning'] = 'Thời gian nghỉ càng ngắn' in response.text
            report['collection_moved_from_posting'] = 'id="view-leads"' in response.text and 'id="collect-all"' not in response.text
            report['posting_summary_only'] = 'id="lead-results"' not in response.text
            lead_page = session.get(url+'/leads', timeout=10)
            report['customer_collection_ui'] = all(marker in lead_page.text for marker in ('id="collection-campaign"', 'id="collection-task"', 'id="collect-selected"', 'id="collection-stop"'))
            report['share_link_input'] = lead_page.status_code == 200 and 'https://www.facebook.com/share/p/' in lead_page.text
            report['customer_hub_ui'] = all(marker in lead_page.text for marker in
                ('id="campaign-filter"', 'id="group-filter"', 'id="interest-filter"', 'id="extra-tools"', 'id="history-box"'))
            customers = session.get(url+'/api/leads/results', timeout=10)
            report['customer_results_api'] = customers.status_code == 200 and customers.json()['records'] == []
            customer_export = session.get(url+'/api/leads/results/excel', timeout=15)
            report['customer_excel'] = customer_export.status_code == 200 and openpyxl.load_workbook(BytesIO(customer_export.content)).active.max_row == 1
            report['common_javascript'] = session.get(url+'/assets/common.js',timeout=10).status_code == 200
            workflow_javascript = session.get(url+'/assets/workflow.js',timeout=10)
            report['workflow_javascript'] = workflow_javascript.status_code == 200
            report['saved_post_comment_button'] = 'Lọc comment tại tab Khách hàng' in workflow_javascript.text and '/comments`' not in workflow_javascript.text
            report['saved_link_check_button'] = 'Kiểm tra link bài này' in workflow_javascript.text and 'post_check_status' in workflow_javascript.text
            quinland_rows = session.get(url+'/api/sources/quinland?limit=250',timeout=15).json()
            report['quinland_catalog'] = isinstance(quinland_rows, list) and len(quinland_rows) == 250
            report['demo_source'] = session.post(url+'/api/sources/demo',headers={'X-Revoland-Client':'local'},timeout=20).status_code == 200
            source_listings = session.get(url+'/api/sources/listings',timeout=10).json()
            report['source_listings'] = len(source_listings) == 2
            source_preview = session.get(url+'/api/sources/listings/'+source_listings[-1]['id']+'/preview',timeout=10).json()
            report['source_preview'] = bool(source_preview.get('preview_token'))
            from PIL import Image
            image_response = session.get(url+source_preview['media_urls'][0],timeout=10)
            with Image.open(BytesIO(image_response.content)) as image:
                report['source_image'] = image_response.status_code == 200 and image.format == 'JPEG'
            headers = {'X-Revoland-Client':'local'}
            group = session.post(url+'/api/groups',headers=headers,
                json={'name':'EXE offline fixture','group_url':'https://www.facebook.com/groups/exe-offline-fixture'},timeout=10).json()['group']
            created = session.post(url+'/api/workflow/campaigns',headers=headers,json={
                'listing_id':source_preview['listing']['id'],'target_group_ids':[group['id']],
                'preview_token':source_preview['preview_token'],'custom_content':source_preview['formatted_text'],
                'image_indices':[0],'reviewed':True, 'min_delay_seconds':42, 'max_delay_seconds':42},timeout=20)
            report['workflow_campaign'] = created.status_code == 200 and created.json()['campaign']['source_mode'] == 'mock'
            campaign = created.json()['campaign']
            report['saved_queue_delay'] = campaign['min_delay_seconds'] == campaign['max_delay_seconds'] == 42
            blocked = session.post(url+'/api/campaigns/'+campaign['id']+'/execute',headers=headers,timeout=10)
            report['demo_post_blocked'] = blocked.status_code != 200
            comments = session.post(url+'/api/workflow/campaigns/'+campaign['id']+'/comments',
                headers=headers, json={'limit':100}, timeout=10)
            report['demo_comments_blocked'] = comments.status_code == 400
            report['no_automatic_comment_collection'] = session.get(url+'/api/leads/runs',timeout=10).json() == []
            javascript = session.get(url+'/assets/leads.js',timeout=10)
            report['javascript'] = javascript.status_code == 200 and '/api/leads/collect' in javascript.text
            customer_css = session.get(url+'/assets/leads.css',timeout=10)
            report['css'] = customer_css.status_code == 200
            report['comment_group_dividers'] = 'customer-comment-group' in javascript.text and '.customer-comment-group{' in customer_css.text
            report['customer_group_column'] = ('<th>Nhóm</th><th>Bình luận</th>' in lead_page.text
                and 'body.colSpan = 2' in javascript.text and '.customer-group-column' in customer_css.text
                and 'customer-comment-group-title' not in customer_css.text)
            report['customer_preview_toggle'] = 'Xem đầy đủ' in javascript.text and 'Thu gọn' in javascript.text and '.customer-preview.is-collapsed' in customer_css.text
            report['search_layout'] = 'flex:1 1 220px' in customer_css.text
            registries = session.get(url+'/api/leads/registries',timeout=10).json()
            report['registry_inventory'] = len(registries) == 5
            config = session.get(url+'/api/config',timeout=10).json()
            report['config_redacted'] = 'revoland_api_key' not in config
            report['removed_content_routes'] = all(session.post(url+path, headers=headers,
                json={'original': 'Nội dung', 'filename': 'tin.txt', 'text': 'Nội dung'}, timeout=10).status_code == 404
                for path in ('/api/content/paraphrase', '/api/content/rewrite-local', '/api/sources/text', '/api/sources/folder'))
            report['removed_config_absent'] = not any(key.startswith('paraphrase') for key in config)
            report['json_import_ui'] = all(marker in response.text for marker in
                ('id="post-json"', 'id="json-import"', '/assets/posts-example.json'))
            json_sample = session.get(url+'/assets/posts-example.json', timeout=10)
            report['json_sample'] = json_sample.status_code == 200 and len(json_sample.json()['posts']) == 2
            json_import = session.post(url+'/api/sources/json', headers=headers,
                json={'filename': 'bai_dang.json', 'data': json_sample.json()}, timeout=15)
            report['json_import'] = json_import.status_code == 200 and len(json_import.json()) == 2
            json_preview = session.get(url+'/api/sources/listings/'+json_import.json()[0]['id']+'/preview', timeout=10).json()
            report['json_preserves_content'] = json_preview['formatted_text'] == json_sample.json()['posts'][0]['content']
            revoland_json = session.post(url+'/api/sources/json', headers=headers, json={
                'filename': 'revoland-response.json', 'data': {'code': 200, 'status': True, 'data': {
                    'id': 'a'*24, 'propertyCode': 'EXE-LINK', 'title': 'Tin Revoland thử nghiệm',
                    'description': '<p>Nội dung thử nghiệm.</p>', 'transactionType': 'ForSale',
                    'status': 'PUBLISH', 'propertyDetails': {'landArea': 52, 'usableArea': 300},
                    'priceDetails': {'salePrice': 12000000000}, 'location': {'address': 'Vị trí mẫu'},
                    'imageUrls': [],
                }}}, timeout=15)
            revoland_preview = session.get(url+'/api/sources/listings/'+revoland_json.json()[0]['id']+'/preview', timeout=10).json()
            report['revoland_json_composition'] = (revoland_json.status_code == 200
                and revoland_preview['listing']['code'] == 'EXE-LINK'
                and 'Giá bán: 12 tỷ' in revoland_preview['formatted_text']
                and 'Diện tích sử dụng: 300 m²' in revoland_preview['formatted_text'])
            many_posts = [{'content': f'Bài mở rộng {i}\n' + ('Nội dung dài ' * 100), 'images': []} for i in range(35)]
            json_bulk = session.post(url+'/api/sources/json', headers=headers,
                json={'filename': 'bulk.json', 'data': {'posts': many_posts}}, timeout=25)
            report['json_unrestricted_bulk'] = json_bulk.status_code == 200 and len(json_bulk.json()) == 35
            html_content = '<p>Nhà đẹp<br><br>72m² &amp; giá 20 tỷ</p>'
            plain_content = 'Nhà đẹp\n\n72m² & giá 20 tỷ'
            html_post = session.post(url+'/api/sources/json', headers=headers,
                json={'filename': 'html.json', 'data': [{'content': html_content}]}, timeout=10).json()[0]
            html_preview = session.get(url+'/api/sources/listings/'+html_post['id']+'/preview', timeout=10).json()
            cleaned = session.post(url+'/api/sources/clean-content', headers=headers,
                json={'content': html_content}, timeout=10).json()
            report['html_post_preview'] = html_preview['formatted_text'] == plain_content
            report['html_clean_button_api'] = cleaned == {'content': plain_content, 'changed': True}
            report['html_clean_button_ui'] = 'id="clean-content"' in response.text
            located_error = session.post(url+'/api/sources/manual', headers=headers,
                json={'title':'Nhà', 'description':'Mô tả', 'area_m2': -1}, timeout=10)
            report['located_validation_error'] = (located_error.status_code == 422
                and located_error.json()['issues'][0]['field'] == 'area_m2')
            bad_json = session.post(url+'/api/sources/json', headers=headers,
                json={'filename':'bad.json','data':[{'content':'Bài hợp lệ'},{'title':'Thiếu nội dung'}]}, timeout=10)
            report['located_json_error'] = (bad_json.status_code == 400
                and bad_json.json()['issues'][0]['location'] == ['data', 1, 'content'])
            common_script = session.get(url+'/assets/common.js', timeout=10).text
            report['automatic_error_focus'] = 'focusInputIssue' in common_script and 'target.focus' in common_script
            listings = session.get(url+'/api/revoland/listings',timeout=10).json()
            report['sample_listings'] = len(listings) == 3 and config['revoland_mock_mode']
            example = session.get(url+'/api/exports/comments/example',timeout=10).json()
            filtered = session.post(url+'/api/leads/filter',json=example,
                headers={'X-Revoland-Client':'local'},timeout=20)
            report['lead_filter'] = filtered.status_code == 200 and filtered.json()['summary']['total'] == len(example)
            negative = session.post(url+'/api/leads/filter', json=[{'text':'xấu vcl nhìn k muốn mua'}], headers=headers, timeout=20)
            report['negated_purchase_filter'] = negative.status_code == 200 and negative.json()['records'][0]['classification'] == 'IGNORE' and negative.json()['records'][0]['score'] == 0
            inquiries = session.post(url+'/api/leads/filter', json=[{'text':'xin hướng nhà'}, {'text':'2 tỷ mua luôn'}], headers=headers, timeout=20)
            report['property_inquiries'] = inquiries.status_code == 200 and [r['classification'] for r in inquiries.json()['records']] == ['NEEDS_REVIEW', 'LEAD_POTENTIAL']
            legal = session.post(url+'/api/leads/filter',
                json=[{'text':'sổ hồng riêng'}, {'text':'sổ hồng riêng, hóng thêm thông tin'}],
                headers=headers, timeout=20).json()['records']
            report['legal_title_interest_context'] = (legal[0]['score'] == 25
                and 'social_engagement' not in legal[0]['signals']['intents']
                and legal[1]['signals']['score_families']['interest'] == 10)
            context_rows = session.post(url+'/api/leads/filter', json=[{'text':'DM me the price'}, {'text':'dm'}, {'text':'2 tỷ mua luôn', 'author':'Anonymous participant'}], headers=headers, timeout=20).json()['records']
            report['context_strength_anonymous'] = [r['interest_level'] for r in context_rows] == ['moderate', 'unclear', 'strong'] and context_rows[2]['identity_status'] == 'anonymous'
            imported = session.post(url+'/api/leads/filter', json=[{'text': text} for text in (
                'có hỗ trợ vay vốn không', 'Nhà này có dính quy hoạch không?',
                'ké chủ tus bên em có căn tương tự 0912345678', 'fix giá giá cuối bớt được không')],
                headers=headers, timeout=20).json()['records']
            report['imported_registry'] = (all(r['registry_version'] == '1.4.0' for r in imported)
                and [r['classification'] for r in imported] == ['NEEDS_REVIEW', 'NEEDS_REVIEW', 'IGNORE', 'NEEDS_REVIEW']
                and imported[-1]['score'] == 30)
            exported = session.post(url+'/api/exports/comments',json=example,
                headers={'X-Revoland-Client':'local'},timeout=30)
            assert exported.status_code == 200
            workbook = openpyxl.load_workbook(BytesIO(exported.content))
            report['comments_excel'] = workbook.active.max_row == len(example)+1
            workbook.close()
            unaccented = session.post(url+'/api/leads/filter', json=[{'text': text} for text in
                ('mua', 'chot gia 2 ty', '2 ty chot gia', 'del mua', 'khong mua', 'chua chot gia')],
                headers=headers, timeout=20).json()['records']
            report['unaccented_purchase'] = [r['classification'] for r in unaccented] == [
                'LEAD_POTENTIAL', 'LEAD_POTENTIAL', 'LEAD_POTENTIAL', 'IGNORE', 'IGNORE', 'IGNORE']
            first_post = 'https://www.facebook.com/groups/fixture/posts/123'
            second_post = 'https://www.facebook.com/groups/fixture2/posts/456'
            customer_comments = [
                {'id':'a', 'author':'Khách thử', 'fb_user_url':'https://www.facebook.com/fixture-customer', 'text':'mua', 'source_url': first_post},
                {'id':'b', 'author':'Khách thử', 'fb_user_url':'https://www.facebook.com/fixture-customer', 'text':'chot gia 2 ty', 'source_url': first_post},
                {'id':'c', 'author':'Khách thử', 'fb_user_url':'https://www.facebook.com/fixture-customer', 'text':'2 ty chot gia', 'source_url': second_post}]
            grouped = session.post(url+'/api/leads/filter', json=customer_comments,
                headers=headers, timeout=20).json()
            report['customer_comment_grouping'] = (grouped['summary']['total'] == 1
                and grouped['records'][0]['comment_count'] == 3 and grouped['records'][0]['group_count'] == 2)
            grouped_excel = session.post(url+'/api/exports/comments', json=customer_comments,
                headers=headers, timeout=30)
            grouped_workbook = openpyxl.load_workbook(BytesIO(grouped_excel.content))
            report['customer_multisource_excel'] = (len(grouped_workbook.worksheets) == 1
                and all(ws.max_row == 2 for ws in grouped_workbook.worksheets)
                and 'chot gia 2 ty' in grouped_workbook.worksheets[0]['K2'].value)
            grouped_workbook.close()
            posts = session.get(url+'/api/exports/campaigns',timeout=30)
            assert posts.status_code == 200
            workbook = openpyxl.load_workbook(BytesIO(posts.content))
            report['posting_excel'] = workbook.active.max_row == 2 and workbook.active['J2'].value == 'pending'
            workbook.close()
            report['passed'] = all(value for key,value in report.items() if key != 'self_test')
            output = executable.parent / 'EXE_VERIFICATION.json'
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False,indent=2))
            print('Verification logs:',runtime)
            return 0 if report['passed'] else 1
        finally:
            stop_process_tree(process)


if __name__ == '__main__':
    raise SystemExit(main())

