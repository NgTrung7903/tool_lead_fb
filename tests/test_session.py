from unittest.mock import Mock
import pytest
from services.facebook_browser import authenticated, profile_operation
from services.session_manager import FacebookSessionManager
from services.poster_engine import FacebookPosterEngine, post_permalink
from services.storage import ResourceBusyError


def test_no_session_never_simulates_success(tmp_path):
    from models.schema import FBGroup
    group = FBGroup(id='g',name='Test',group_url='https://www.facebook.com/groups/test')
    result = FacebookPosterEngine(tmp_path / 'empty').post_to_single_group('t',group,'Text',[])
    assert result.status.value == 'action_required'
    assert result.post_url is None


def test_cookie_and_ui_both_required():
    page, context = Mock(), Mock()
    page.url = 'https://www.facebook.com/'
    context.cookies.return_value = []
    assert not authenticated(page, context)
    context.cookies.return_value = [{'name':'c_user','value':'123'}]
    page.locator.return_value.count.return_value = 0
    assert not authenticated(page, context)
    page.url = 'https://www.facebook.com/checkpoint/123'
    assert not authenticated(page, context)


def test_profile_lock_protects_logout_and_check(tmp_path):
    manager = FacebookSessionManager(tmp_path / 'profile')
    with profile_operation(manager.profile_dir):
        with pytest.raises(ResourceBusyError): manager.logout_and_clear_session()
        status = manager.check_session_status()
        assert status.busy and not status.is_authenticated


def test_logout_reports_deletion_failure(tmp_path, monkeypatch):
    directory = tmp_path / 'profile'; directory.mkdir()
    manager = FacebookSessionManager(directory)
    monkeypatch.setattr('services.session_manager.shutil.rmtree', Mock(side_effect=PermissionError('locked')))
    with pytest.raises(PermissionError): manager.logout_and_clear_session()
    assert directory.exists()


@pytest.mark.parametrize('value', ['https://evil.test/groups/test/posts/123','https://www.facebook.com/groups/other/posts/123','https://www.facebook.com/groups/test'])
def test_post_url_must_be_permalink_for_same_group(value):
    assert post_permalink(value,'https://www.facebook.com/groups/test') is None


def test_password_saving_disabled_preserves_preferences(tmp_path):
    import json
    from services.facebook_browser import launch_context
    preferences = tmp_path/'Default'/'Preferences';preferences.parent.mkdir()
    preferences.write_text(json.dumps({'profile':{'name':'Customer'},'other':'keep'}),encoding='utf-8')
    playwright = Mock()
    launch_context(playwright,tmp_path,True)
    saved = json.loads(preferences.read_text(encoding='utf-8'))
    assert saved['credentials_enable_service'] is False
    assert saved['profile']['password_manager_enabled'] is False
    assert saved['profile']['name'] == 'Customer' and saved['other'] == 'keep'


def test_quick_status_never_launches_playwright(tmp_path, monkeypatch):
    monkeypatch.setattr('services.session_manager.sync_playwright', Mock(side_effect=AssertionError('must not launch browser')))
    manager = FacebookSessionManager(tmp_path / 'profile')
    assert not manager.quick_status().is_authenticated
    assert 'Chưa đăng nhập' in manager.quick_status().status_text
    manager.profile_dir.mkdir()
    (manager.profile_dir / 'Cookies').write_text('saved', encoding='utf-8')
    assert 'Kiểm tra' in manager.quick_status().status_text
    manager._last_valid = True
    assert manager.quick_status().is_authenticated
