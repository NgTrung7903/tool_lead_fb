from contextlib import nullcontext
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
import pytest
from playwright.sync_api import sync_playwright

from services import page_post_service as module
from services.page_post_service import PagePostService, FacebookPagePoster, page_identity, page_permalink


@pytest.mark.parametrize('url', ['https://evil.test/profile.php?id=123', 'http://facebook.com/profile.php?id=123',
    'https://facebook.com/groups/123', 'https://a:b@facebook.com/profile.php?id=123'])
def test_page_url_rejects_wrong_kind_or_host(url):
    with pytest.raises(ValueError): page_identity(url)


def test_page_links_are_scoped_to_page_id():
    assert page_identity('https://www.facebook.com/people/Example/123/')[0] == '123'
    assert page_permalink('https://www.facebook.com/permalink.php?story_fbid=pfbid1&id=123', '123')
    assert not page_permalink('https://www.facebook.com/permalink.php?story_fbid=pfbid1&id=999', '123')


def prepare(service, tmp_path):
    source = tmp_path/'source.json'
    source.write_text(json.dumps([{'title':'Căn thử', 'status':'ARCHIVED', 'images':[],
        'propertyDetails':{'buildingArea':61.4},'priceDetails':{'salePrice':2950000000},
        'privateNote':'SECRET_NOTE','contactPhone':'PRIVATE_PHONE'}]), encoding='utf-8')
    return service.prepare(source, 'https://www.facebook.com/people/Test/123/', 'Test Page')


def test_archived_test_is_explicit_and_never_copies_private_fields(tmp_path):
    service = PagePostService(tmp_path/'runs')
    run = prepare(service, tmp_path)
    assert run['status'] == 'prepared' and not run['submission_started']
    assert run['source_status'] == 'ARCHIVED' and 'ARCHIVED' in run['content']
    assert 'KIỂM THỬ TOOL' in run['content']
    assert 'SECRET_NOTE' not in str(run) and 'PRIVATE_PHONE' not in str(run)


def test_failure_after_submit_checkpoint_is_unknown_and_not_repeated(tmp_path):
    poster = Mock()
    def crash(run, before_submit, proof_dir):
        before_submit()
        raise RuntimeError('disconnected after submit')
    poster.publish.side_effect = crash
    service = PagePostService(tmp_path/'runs', poster)
    run = prepare(service, tmp_path)
    result = service.submit(run['id'])
    assert result['status'] == 'unknown' and result['submission_started']
    with pytest.raises(ValueError, match='không tự gửi lại'): service.submit(run['id'])
    assert poster.publish.call_count == 1


def test_missing_session_can_be_retried_only_before_submit(tmp_path):
    poster = Mock()
    poster.publish.return_value = {'status':'action_required','submission_started':False}
    service = PagePostService(tmp_path/'runs', poster)
    run = prepare(service, tmp_path)
    assert service.submit(run['id'])['status'] == 'action_required'
    assert not service.get(run['id'])['submission_started']


@pytest.mark.browser
def test_page_poster_runs_real_dom_upload_next_submit_and_permalink(tmp_path, monkeypatch):
    image_path = tmp_path/'fixture.jpg'
    Image.new('RGB',(10,10),'red').save(image_path)
    content = 'KIỂM THỬ TOOL — fixture\nNội dung duyệt đầy đủ.'
    html = '''<!doctype html><meta charset="utf-8"><nav role="navigation">Profile</nav>
      <button onclick="document.querySelector('#compose').style.display='block'">Bạn đang nghĩ gì?</button>
      <div role="dialog" id="compose" style="display:none"><p>Test Page</p><div role="textbox" contenteditable="true"></div>
      <input id="files" type="file" style="display:none" accept="image/*" multiple onchange="for(const f of this.files){const img=document.createElement('img');img.alt=f.name;const reader=new FileReader();reader.onload=()=>img.src=reader.result;reader.readAsDataURL(f);this.parentNode.append(img);}">
      <button onclick="document.querySelector('#files').click()">Ảnh/video</button>
      <button onclick="window.approved=document.querySelector('[role=textbox]').innerText;document.querySelector('#compose').style.display='none';document.querySelector('#preview').textContent=window.approved;document.querySelector('#settings').style.display='block'">Tiếp</button></div>
      <div role="dialog" id="settings" style="display:none"><p id="preview"></p><button onclick="send()">Đăng</button></div>
      <script>function send(){document.querySelector('#settings').style.display='none';let article=document.createElement('div');article.setAttribute('role','article');let p=document.createElement('p');p.textContent=window.approved;article.append(p);let a=document.createElement('a');a.textContent='Vừa xong';a.href='/permalink.php?story_fbid=fixture1&id=123';a.onclick=e=>{e.preventDefault();history.pushState({},'',a.href)};article.append(a);let photo=document.createElement('a');photo.href='/photo/?fbid=1';photo.textContent='Photo';article.append(photo);document.body.append(article);window.captureSubmission();}</script>'''
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies([{'name':'c_user','value':'fixture','domain':'.facebook.com','path':'/'}])
        context.route('**/*', lambda route: route.fulfill(content_type='text/html',body=html))
        capture = Mock()
        context.expose_binding('captureSubmission',lambda *args:capture())
        monkeypatch.setattr(module,'sync_playwright',lambda:nullcontext(Mock()))
        monkeypatch.setattr(module,'launch_context',lambda *args:context)
        poster = FacebookPagePoster(tmp_path/'profile')
        poster.confirmation_timeout = 3
        before = Mock()
        result = poster.publish({'page_url':'https://www.facebook.com/profile.php?id=123','page_name':'Test Page',
            'content':content,'images':[{'path':str(image_path)}]}, before, tmp_path)
        if result['status'] != 'posted':
            print(json.dumps(result, ensure_ascii=True))
        assert result['status'] == 'posted', result
        assert result['post_url'].endswith('story_fbid=fixture1&id=123')
        before.assert_called_once()
        capture.assert_called_once()
        assert (tmp_path/'posted.png').exists()
        browser.close()
