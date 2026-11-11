"""Offline browser tests. All HTTP requests are intercepted; no real Facebook actions."""
import json
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import Mock
import threading
from types import SimpleNamespace

import pytest
from playwright.sync_api import sync_playwright
from models.schema import FBGroup
from services.poster_engine import FacebookPosterEngine

pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def install_offline_workers(monkeypatch, route_handler, on_submit=None):
    launches = []

    @contextmanager
    def isolated_context(storage_state, headless):
        # Each worker gets real Playwright objects owned by that worker's thread.
        with sync_playwright() as playwright:
            worker_browser = playwright.chromium.launch(headless=True)
            try:
                context = worker_browser.new_context(storage_state=storage_state)
                context.route('**/*', route_handler)
                if on_submit:
                    context.expose_binding('captureSubmission', on_submit)
                launches.append(threading.get_ident())
                yield context
            finally:
                worker_browser.close()

    monkeypatch.setattr('services.facebook_browser.isolated_posting_context', isolated_context)
    return launches


@pytest.mark.parametrize('scenario,expected', [
    ('available', 'available'), ('unavailable', 'unavailable'), ('checkpoint', 'action_required'),
    ('other_post', 'unknown'), ('blank', 'unknown'), ('network', 'unknown')])
def test_check_saved_link_does_not_post_or_confuse_other_posts(browser, tmp_path, scenario, expected):
    context = browser.new_context()
    context.add_cookies([{'name': 'c_user', 'value': 'fixture', 'domain': '.facebook.com', 'path': '/'}])
    url = 'https://www.facebook.com/groups/test/posts/123'
    html = '<nav role="navigation">Account</nav>'
    if scenario == 'unavailable':
        html += '<h2>This content isn\'t available right now</h2>'
    elif scenario == 'checkpoint':
        html += '<input name="email"><input name="pass">'
    elif scenario in ('available', 'other_post'):
        link = url if scenario == 'available' else url.replace('/123', '/999')
        html += f'<div role="article"><p>Approved content</p><a href="{link}">1 h</a></div>'
    def serve(route):
        if scenario == 'network':
            return route.abort()
        route.fulfill(content_type='text/html', body=html)
    context.route('**/*', serve)
    page = context.new_page()
    session = SimpleNamespace(next_page=lambda: (context, page))
    result = FacebookPosterEngine(tmp_path/'profile').check_saved_post(
        url, FBGroup(id='g', name='Test', group_url='https://www.facebook.com/groups/test'),
        'Approved content', shared_session=session)
    assert result['status'] == expected, result
    context.close()


def fixture_html(outcome, old_notice=False):
    return '''<!doctype html><html lang="vi"><meta charset="utf-8">
      <nav role="navigation">Account</nav><div role="feed"></div>
      <button onclick="document.querySelector('[role=dialog]').style.display='block'">Write something</button>
      <div role="status" id="notice">''' + ('Your post is pending approval' if old_notice else '') + '''</div>
      <div role="dialog" style="display:none">
        <div role="textbox" contenteditable="true"></div>
        <input type="file" accept="image/*" multiple onchange="for(const file of this.files){let tile=document.createElement('div');let img=document.createElement('img');let remove=document.createElement('button');remove.setAttribute('aria-label','Remove photo');remove.textContent='Remove';tile.append(img,remove);let reader=new FileReader();reader.onload=()=>img.src=reader.result;reader.readAsDataURL(file);this.parentNode.append(tile)}">
        <button id="submit" onclick="send()">Post</button>
      </div>
      <script>
      function send(){
        let text=document.querySelector('[role=textbox]').innerText;
        document.querySelector('[role=dialog]').style.display='none';
        window.sentText=text; window.sentFiles=document.querySelector('input').files.length;
        if(window.captureSubmission) window.captureSubmission({text:text,files:window.sentFiles});
        let outcome=''' + json.dumps(outcome) + ''';
        if(outcome==='posted'){
          let article=document.createElement('div');article.setAttribute('role','article');
          let content=document.createElement('p');content.textContent=text;article.append(content);
          let link=document.createElement('a');link.href='/groups/test/posts/12345';link.textContent='Just now';article.append(link);document.body.append(article);
        }else if(outcome==='pending') document.querySelector('#notice').textContent='Your post is pending approval';
        else if(outcome==='disconnect') window.location.href='/checkpoint/123';
      }
      </script></html>'''


@pytest.mark.parametrize('outcome,expected',[('posted','posted'),('pending','pending_approval'),('disconnect','unknown')])
def test_poster_full_text_images_and_real_confirmation(browser, monkeypatch, tmp_path, outcome, expected):
    context = browser.new_context()
    context.add_cookies([{'name':'c_user','value':'test-user','domain':'.facebook.com','path':'/'}])
    def fixture_route(route):
        route.fulfill(content_type='text/html',body=fixture_html(outcome))
    context.route('**/*', fixture_route)
    # Supply a fixture context to the actual engine; its browser operations remain real.
    monkeypatch.setattr('services.poster_engine.launch_context',lambda *a,**kw:context)
    monkeypatch.setattr('services.poster_engine.sync_playwright', lambda: nullcontext(Mock()))
    page_ref = []
    original_new_page = context.new_page
    def new_page():
        page = original_new_page()
        goto = page.goto
        def fixture_goto(url, **kwargs):
            return goto(url, **{**kwargs, 'timeout':5000})
        monkeypatch.setattr(page,'goto',fixture_goto)
        page_ref.append(page)
        return page
    monkeypatch.setattr(context,'new_page',new_page)
    captured = {}
    context.expose_binding('captureSubmission', lambda source, payload: captured.update(payload))
    profile = tmp_path/'profile';profile.mkdir();(profile/'marker').write_text('fixture')
    from PIL import Image
    image = tmp_path/'image.jpg'; Image.new('RGB',(10,10),'red').save(image)
    content = 'Nội dung dài đã duyệt 🏡\n' + ('Thông tin căn hộ và pháp lý từ API. ' * 30) + '\n☎ 0912345678'
    before = Mock()
    group = FBGroup(id='g',name='Fixture',group_url='https://www.facebook.com/groups/test')
    engine = FacebookPosterEngine(profile)
    engine.upload_timeout = 3
    engine.confirmation_timeout = 3
    result = engine.post_to_single_group('t',group,content,[str(image)],before_submit=before)
    assert result.status.value == expected, (result.model_dump(), captured)
    before.assert_called_once()
    if outcome != 'disconnect':
        assert captured['text'].replace('\xa0',' ') == content
        assert captured['files'] == 1
    if outcome == 'posted':
        assert result.post_url.endswith('/posts/12345') and result.evidence


def test_dashboard_renders_untrusted_data_as_text(browser):
    context = browser.new_context()
    page = context.new_page()
    root = Path(__file__).resolve().parent.parent
    listing = {'id':'l','title':'<img src=x onerror="window.injected=1">','code':'A', 'price_text':'1 tỷ', 'location':'HCM','media_urls':[]}
    def route(request):
        url = request.request.url
        if not url.startswith('http://localhost:8000/'):
            return request.fulfill(status=200, body='')
        if url.endswith('/assets/app.js'):
            return request.fulfill(content_type='application/javascript',body=(root/'api/static/app.js').read_text(encoding='utf-8'))
        if '/api/' not in url:
            return request.fulfill(content_type='text/html',body=(root/'api/static/index.html').read_text(encoding='utf-8'))
        if url.endswith('/api/session/status'): data={'is_authenticated':False,'status_text':'Login required','busy':False}
        elif url.endswith('/api/config'): data={'revoland_mock_mode':True}
        elif url.endswith('/api/revoland/listings'): data=[listing]
        elif url.endswith('/preview'): data={'formatted_text':'Preview','media_urls':[],'preview_token':'fixture'}
        else: data=[]
        request.fulfill(content_type='application/json',body=json.dumps(data))
    context.route('**/*',route)
    page.goto('http://localhost:8000/posting')
    page.wait_for_function("document.getElementById('preview-post-text').value === 'Preview'")
    assert page.locator('[data-listing]').inner_text().startswith('<img')
    assert page.evaluate('window.injected') is None
    assert page.locator('#btn-start-posting').is_disabled()
    context.close()


def test_dashboard_to_api_to_sqlite_and_reload(browser, monkeypatch, tmp_path):
    """Real dashboard + real FastAPI handlers + real SQLite; external systems replaced."""
    from fastapi.testclient import TestClient
    from api import server
    from models.schema import PropertyListing, GroupTaskResult, GroupPostStatusEnum as S, SessionStatus
    from services.campaign_service import CampaignService
    from services.group_manager import GroupManager
    revo = Mock()
    cfg = {'revoland_mock_mode':False, 'revoland_api_key':'secret-fixture', 'min_delay_seconds':0,'max_delay_seconds':0}
    revo.config = cfg
    listing = PropertyListing(id='live-fixture',code='A',title='Căn kiểm thử',price_text='1 tỷ',location='HCM',description='API description',media_urls=[])
    revo.get_listings.return_value = [listing]
    revo.get_listing_by_id.return_value = listing
    revo.download_listing_images.return_value = []
    revo.format_post_content.return_value = 'Nội dung từ API'
    groups = GroupManager(tmp_path/'groups.json')
    group = groups.add_group('Nhóm kiểm thử','https://facebook.com/groups/fixture')
    poster = Mock()
    def submit(**kw):
        kw['before_submit']()
        return GroupTaskResult(task_id=kw['task_id'],group_id=group.id,group_name=group.name,group_url=group.group_url,
            status=S.POSTED,post_url=group.group_url+'/posts/123',evidence='offline_fixture',submission_started=True)
    poster.post_to_single_group.side_effect = submit
    campaigns = CampaignService(revo,groups,poster,tmp_path/'history.sqlite3')
    campaigns.config.update(min_delay_seconds=0,max_delay_seconds=0)
    monkeypatch.setattr(server,'revoland_service',revo)
    monkeypatch.setattr(server,'group_manager',groups)
    monkeypatch.setattr(server,'campaign_service',campaigns)
    monkeypatch.setattr(server,'load_config',lambda:cfg)
    monkeypatch.setattr(server.session_manager,'check_session_status',lambda:SessionStatus(is_authenticated=True,status_text='Fixture ready',profile_dir='fixture'))
    client = TestClient(server.app,base_url='http://localhost:8000')
    context = browser.new_context()
    failures, errors = [], []
    def actual_api(route):
        req = route.request
        if not req.url.startswith('http://localhost:8000/'):
            return route.fulfill(status=200,body='')
        response = client.request(req.method, req.url, headers=req.all_headers(), content=req.post_data)
        if response.status_code >= 400: failures.append((req.url,response.status_code))
        route.fulfill(status=response.status_code,headers=dict(response.headers),body=response.content)
    context.route('**/*',actual_api)
    page = context.new_page()
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://localhost:8000/posting')
    page.wait_for_function("!document.getElementById('btn-start-posting').disabled")
    approved = 'Nội dung đã duyệt 🏡\n' + 'Chi tiết căn hộ. ' * 70 + '\n☎ 0912345678'
    page.locator('#preview-post-text').fill(approved)
    page.locator('.group-checkbox').check()
    page.locator('#btn-start-posting').click()
    page.wait_for_function("document.getElementById('results-table-body').innerText.includes('Đã xác nhận đăng')")
    saved = campaigns.list_campaigns()[0]
    assert saved.formatted_content == approved
    assert saved.tasks[0].status == S.POSTED
    assert poster.post_to_single_group.call_count == 1
    page.reload()
    page.wait_for_function("document.getElementById('results-table-body').innerText.includes('Đã xác nhận đăng')")
    assert page.locator('#campaign-history').input_value() == saved.id
    # Download real files through the actual dashboard buttons and API handlers.
    import openpyxl
    from io import BytesIO
    with page.expect_download() as download:
        page.locator('#btn-export-campaign').click()
    assert download.value.suggested_filename == 'ket_qua_dang_bai.xlsx'
    exported = openpyxl.load_workbook(BytesIO(download.value.path().read_bytes())).active
    assert exported['J2'].value == 'posted'
    assert exported['K2'].value.endswith('/posts/123')
    with page.expect_download() as all_download:
        page.locator('#btn-export-all').click()
    assert openpyxl.load_workbook(BytesIO(all_download.value.path().read_bytes())).active.max_row == 2
    page.locator('#comments-json-file').set_input_files({'name':'comments.json','mimeType':'application/json',
        'buffer':json.dumps([{'author':'Khách mẫu','text':'Cần mua 0912345678'}]).encode('utf-8')})
    with page.expect_download() as comments_download:
        page.locator('#btn-export-comments').click()
    assert comments_download.value.suggested_filename == 'binh_luan_lead.xlsx'
    comments_sheet = openpyxl.load_workbook(BytesIO(comments_download.value.path().read_bytes())).active
    assert comments_sheet['E2'].value == '0912345678'
    assert comments_sheet['N2'].value == 'Lead tiềm năng'
    page.locator('#comments-json-file').set_input_files({'name':'invalid.json','mimeType':'application/json','buffer':b'not json'})
    page.locator('#btn-export-comments').click()
    page.wait_for_function("document.getElementById('export-status').innerText.includes('JSON hợp lệ')")
    assert not failures and not errors
    context.close()


def run_photo_fixture(browser, monkeypatch, tmp_path, html, image_count):
    """Use real DOM/file inputs with no network, credentials or real Facebook actions."""
    from PIL import Image
    context = browser.new_context()
    context.add_cookies([{'name':'c_user','value':'fixture','domain':'.facebook.com','path':'/'}])
    context.route('**/*',lambda route: route.fulfill(content_type='text/html',body=html))
    monkeypatch.setattr('services.poster_engine.launch_context',lambda *args,**kw:context)
    monkeypatch.setattr('services.poster_engine.sync_playwright',lambda:nullcontext(Mock()))
    profile = tmp_path/'profile';profile.mkdir();(profile/'marker').write_text('fixture')
    images = []
    for index in range(image_count):
        path = tmp_path/f'image-{index}.jpg'
        Image.new('RGB',(12,12),'red').save(path)
        images.append(str(path))
    engine = FacebookPosterEngine(profile)
    engine.upload_timeout = 1
    engine.confirmation_timeout = 2
    before = Mock()
    try:
        result = engine.post_to_single_group('task',FBGroup(id='g',name='Fixture',group_url='https://www.facebook.com/groups/test'),
            'Approved content',images,before_submit=before)
        return result, before
    finally:
        context.close()


@pytest.mark.parametrize('image_count,upload_count,expected',[(1,0,'failed'),(2,0,'failed'),(2,1,'failed'),(2,2,'posted')])
def test_avatar_does_not_count_as_uploaded_photos(browser, monkeypatch, tmp_path, image_count, upload_count, expected):
    html = fixture_html('posted')
    html = html.replace('<div role="dialog" style="display:none">',
        '<div role="dialog" style="display:none"><img src="https://scontent.fixture/avatar.jpg" alt="Avatar">')
    html = html.replace('for(const file of this.files)',f'for(const file of Array.from(this.files).slice(0,{upload_count}))')
    result, before = run_photo_fixture(browser,monkeypatch,tmp_path,html,image_count)
    assert result.status.value == expected
    assert before.call_count == (1 if expected == 'posted' else 0)


@pytest.mark.parametrize('condition',['broken','uploading','unscoped','draft'])
def test_unconfirmed_or_existing_photos_block_submit(browser, monkeypatch, tmp_path, condition):
    html = fixture_html('posted')
    if condition == 'broken':
        html = html.replace('reader.onload=()=>img.src=reader.result','reader.onload=()=>img.src="data:image/png;base64,broken"')
    elif condition == 'uploading':
        html = html.replace('<div role="textbox"', '<div role="progressbar">Uploading</div><div role="textbox"')
    elif condition == 'unscoped':
        html = html.replace("remove.setAttribute('aria-label','Remove photo');",'')
    else:
        html = html.replace('<div role="textbox"',
            '<div><img src="https://scontent.fixture/old-photo.jpg"><button aria-label="Remove photo">Remove</button></div><div role="textbox"')
    result, before = run_photo_fixture(browser,monkeypatch,tmp_path,html,1)
    assert result.status.value == 'failed'
    before.assert_not_called()


def test_real_comet_collage_upload_expand_and_pcb_permalink(browser, monkeypatch, tmp_path):
    """Regression test matching modern Vietnamese Facebook Comet group DOM."""
    html = '''<!doctype html><html lang="vi"><meta charset="utf-8">
      <nav role="navigation">Account</nav>
      <div role="main">
        <div role="button" onclick="document.querySelector('[role=dialog]').style.display='block'">Bạn viết gì đi...</div>
        <div role="feed" id="feed"></div>
      </div>
      <div role="dialog" style="display:none">
        <img src="https://static.xx.fbcdn.net/rsrc.php/yY/r/w9q.webp" alt="Nhóm công khai">
        <div role="textbox" contenteditable="true"></div>
        <div id="collage"></div>
        <input id="fb-file" type="file" accept="image/*" multiple style="display:none" onchange="
          const box = document.getElementById('collage');
          box.innerHTML = '';
          const rm = document.createElement('div');
          rm.setAttribute('role', 'button');
          rm.setAttribute('aria-label', 'Gỡ file đính kèm trong bài viết');
          box.appendChild(rm);
          for (const f of this.files) {
            const img = document.createElement('img');
            img.alt = f.name;
            const r = new FileReader();
            r.onload = () => { img.src = r.result; document.getElementById('post-btn').removeAttribute('aria-disabled'); };
            r.readAsDataURL(f);
            box.appendChild(img);
          }
        ">
        <div role="button" aria-label="Ảnh/video" onclick="document.getElementById('fb-file').click()"></div>
        <div id="post-btn" role="button" aria-label="Đăng" aria-disabled="true" onclick="publish()">Đăng</div>
      </div>
      <script>
      function publish() {
        const full = document.querySelector('[role=textbox]').innerText;
        document.querySelector('[role=dialog]').style.display = 'none';
        const item = document.createElement('div');
        const body = document.createElement('div');
        const lines = full.split('\\n');
        body.textContent = lines[0] + '... ';
        const more = document.createElement('div');
        more.setAttribute('role', 'button');
        more.textContent = 'Xem thêm';
        more.onclick = () => { body.textContent = full; more.remove(); };
        item.append(body, more);
        const photo = document.createElement('a');
        photo.href = 'https://www.facebook.com/photo/?fbid=111&set=pcb.99887766';
        photo.textContent = 'Ảnh';
        item.appendChild(photo);
        document.getElementById('feed').appendChild(item);
      }
      </script></html>'''
    result, before = run_photo_fixture(browser, monkeypatch, tmp_path, html, 3)
    assert result.status.value == 'posted', result.model_dump()
    assert result.post_url == 'https://www.facebook.com/groups/test/posts/99887766'
    before.assert_called_once()


def test_comet_large_photo_collage_plus_badge(browser, monkeypatch, tmp_path):
    """When > 5 photos are attached, Facebook renders 5 preview tiles plus a +N badge."""
    html = '''<!doctype html><html lang="vi"><meta charset="utf-8">
      <nav role="navigation">Account</nav>
      <div role="main">
        <div role="button" onclick="document.querySelector('[role=dialog]').style.display='block'">Bạn viết gì đi...</div>
        <div role="feed" id="feed"></div>
      </div>
      <div role="dialog" style="display:none">
        <div role="textbox" contenteditable="true"></div>
        <div id="collage"></div>
        <input id="fb-file" type="file" accept="image/*" multiple style="display:none" onchange="
          const box = document.getElementById('collage');
          box.innerHTML = '';
          const rm = document.createElement('div');
          rm.setAttribute('role', 'button');
          rm.setAttribute('aria-label', 'Gỡ file đính kèm trong bài viết');
          box.appendChild(rm);
          const all = Array.from(this.files);
          for (const f of all.slice(0, 5)) {
            const img = document.createElement('img');
            const r = new FileReader();
            r.onload = () => { img.src = r.result; document.getElementById('post-btn').removeAttribute('aria-disabled'); };
            r.readAsDataURL(f);
            box.appendChild(img);
          }
          if (all.length > 5) {
            const badge = document.createElement('span');
            badge.textContent = '+' + (all.length - 4);
            box.appendChild(badge);
          }
        ">
        <div role="button" aria-label="Ảnh/video" onclick="document.getElementById('fb-file').click()"></div>
        <div id="post-btn" role="button" aria-label="Đăng" aria-disabled="true" onclick="
          const full = document.querySelector('[role=textbox]').innerText;
          document.querySelector('[role=dialog]').style.display = 'none';
          const item = document.createElement('div');
          item.textContent = full;
          const photo = document.createElement('a');
          photo.href = 'https://www.facebook.com/photo/?fbid=222&set=pcb.555444';
          photo.textContent = 'Ảnh';
          item.appendChild(photo);
          document.getElementById('feed').appendChild(item);
        ">Đăng</div>
      </div></html>'''
    result, before = run_photo_fixture(browser, monkeypatch, tmp_path, html, 15)
    assert result.status.value == 'posted', result.model_dump()
    assert result.post_url == 'https://www.facebook.com/groups/test/posts/555444'
    before.assert_called_once()


def test_same_account_posts_to_5_groups_in_sequence(browser, monkeypatch, tmp_path):
    """The real campaign queue posts all selected groups one after another."""
    from models.schema import PropertyListing
    from services.campaign_service import CampaignService
    from services.group_manager import GroupManager

    def multi_group_route(route):
        slug = route.request.url.rstrip('/').split('/')[-1]
        html = fixture_html('posted').replace('/groups/test/posts/12345', f'/groups/{slug}/posts/900{slug}')
        route.fulfill(content_type='text/html', body=html)

    launch_calls = []

    def fake_launch(*args, **kwargs):
        launch_calls.append(1)
        context = browser.new_context()
        context.add_cookies([{'name': 'c_user', 'value': 'test-user', 'domain': '.facebook.com', 'path': '/'}])
        context.route('**/*', multi_group_route)
        return context

    monkeypatch.setattr('services.poster_engine.launch_context', fake_launch)
    monkeypatch.setattr('services.poster_engine.sync_playwright', lambda: nullcontext(Mock()))

    profile = tmp_path / 'profile'
    profile.mkdir()
    (profile / 'marker').write_text('fixture')

    groups_mgr = GroupManager(tmp_path / 'groups.json')
    created_groups = [
        groups_mgr.add_group(f'Nhóm {i}', f'https://www.facebook.com/groups/nhom{i}')
        for i in range(1, 6)
    ]

    revo = Mock()
    revo.config = {'revoland_mock_mode': False}
    revo.get_listing_by_id.return_value = PropertyListing(
        id='ql_multi', code='QL', title='Căn hộ Quận 7',
        price_text='4,2 tỷ', location='Quận 7', description='Mô tả', media_urls=[],
    )
    revo.format_post_content.return_value = 'Bán căn hộ Quận 7 giá tốt 4,2 tỷ'
    revo.download_listing_images.return_value = []

    engine = FacebookPosterEngine(profile)
    engine.upload_timeout = 3
    engine.confirmation_timeout = 3
    svc = CampaignService(revo, groups_mgr, engine, tmp_path / 'campaigns.sqlite3')
    svc.config.update(min_delay_seconds=0, max_delay_seconds=0, max_groups_per_batch=5)

    camp = svc.create_campaign('ql_multi', [g.id for g in created_groups])
    done = svc.execute_campaign(camp.id)

    assert len(launch_calls) == 5
    assert done.status == 'completed'
    assert [t.status.value for t in done.tasks] == ['posted'] * 5
    assert [t.post_url for t in done.tasks] == [
        f'https://www.facebook.com/groups/nhom{i}/posts/900nhom{i}' for i in range(1, 6)
    ]


def test_sequential_groups_emoji_stripping_and_chronological_auto_verify(browser, monkeypatch, tmp_path):
    """Emojis and delayed chronological feed appearance across sequential groups."""
    from models.schema import PropertyListing
    from services.campaign_service import CampaignService
    from services.group_manager import GroupManager

    submitted_slugs = set()

    def delayed_route(route):
        url = route.request.url
        slug = url.split('/groups/')[1].split('?')[0].split('/')[0] if '/groups/' in url else 'g1'
        if 'sorting_setting=CHRONOLOGICAL' in url and slug in submitted_slugs:
            # Facebook stripped emojis into <img> tags and injected \u200e/\u034f marks!
            chrono_html = '''<!doctype html><html lang="vi"><meta charset="utf-8">
              <nav role="navigation">Account</nav>
              <div role="main"><div role="feed">
                <div>
                  <div>BÁN CĂN HỘ 1PN1WC Origami\u200e\u034f</div>
                  <div>Giá: 2,35 tỷ · Mã căn: S9 tầng 03</div>
                  <a href="https://www.facebook.com/photo/?fbid=11&set=pcb.777888">Ảnh</a>
                </div>
              </div></div></html>'''
            route.fulfill(content_type='text/html', body=chrono_html)
            return
        # Initial group page does NOT render the post in the DOM after submit (forcing chronological auto-check!)
        base_html = fixture_html('none').replace(
            'function send(){',
            f'function send(){{ if(window.markSlug) window.markSlug({json.dumps(slug)}); ',
        )
        route.fulfill(content_type='text/html', body=base_html)

    def launch(*args, **kwargs):
        context = browser.new_context()
        context.add_cookies([{'name': 'c_user', 'value': 'test-user', 'domain': '.facebook.com', 'path': '/'}])
        context.route('**/*', delayed_route)
        context.expose_binding('markSlug', lambda source, slug: submitted_slugs.add(slug))
        return context
    monkeypatch.setattr('services.poster_engine.launch_context', launch)
    monkeypatch.setattr('services.poster_engine.sync_playwright', lambda: nullcontext(Mock()))

    profile = tmp_path / 'profile'
    profile.mkdir()
    (profile / 'marker').write_text('fixture')

    groups_mgr = GroupManager(tmp_path / 'groups.json')
    g1 = groups_mgr.add_group('Group 1', 'https://www.facebook.com/groups/alpha')
    g2 = groups_mgr.add_group('Group 2', 'https://www.facebook.com/groups/beta')

    revo = Mock()
    revo.config = {'revoland_mock_mode': False}
    revo.get_listing_by_id.return_value = PropertyListing(
        id='ql_origami', code='QL', title='Origami',
        price_text='2,35 tỷ', location='Thủ Đức', description='Mô tả', media_urls=[],
    )
    revo.format_post_content.return_value = '🏡 BÁN CĂN HỘ 1PN1WC Origami\n💰 Giá: 2,35 tỷ · ✅ Mã căn: S9 tầng 03'
    revo.download_listing_images.return_value = []

    engine = FacebookPosterEngine(profile)
    engine.upload_timeout = 2
    engine.confirmation_timeout = 10
    svc = CampaignService(revo, groups_mgr, engine, tmp_path / 'campaigns.sqlite3')
    svc.config.update(min_delay_seconds=0, max_delay_seconds=0, max_groups_per_batch=5)

    camp = svc.create_campaign('ql_origami', [g1.id, g2.id])
    done = svc.execute_campaign(camp.id)

    assert submitted_slugs == {'alpha', 'beta'}
    assert done.status == 'completed'
    assert [t.status.value for t in done.tasks] == ['posted', 'posted']
    assert done.tasks[0].post_url == 'https://www.facebook.com/groups/alpha/posts/777888'
    assert done.tasks[1].post_url == 'https://www.facebook.com/groups/beta/posts/777888'
