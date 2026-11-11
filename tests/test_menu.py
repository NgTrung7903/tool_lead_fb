import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from menu import ROOT, ToolMenu


def test_exit_does_not_start_browser_or_create_customer_data(tmp_path):
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path))
    result = subprocess.run([sys.executable, str(ROOT/'menu.py')], input='0\n',
        text=True, encoding='utf-8', capture_output=True, cwd=ROOT, env=env, timeout=15)
    assert result.returncode == 0
    assert 'MENU CHÍNH' in result.stdout
    assert not (tmp_path/'RevolandFBPoster').exists()


def test_child_uses_exact_arguments_and_selected_customer(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    child = Mock()
    child.wait.return_value = 0
    launch = Mock(return_value=child)
    monkeypatch.setattr('menu.subprocess.Popen', launch)
    menu = ToolMenu('page-test')
    menu.cli('--export-comments', r'C:\Data With Spaces\comments.json')
    args, kwargs = launch.call_args
    assert args[0][-1] == r'C:\Data With Spaces\comments.json'
    assert kwargs['shell'] is False
    assert kwargs['env']['REVOLAND_DATA_DIR'] == str(tmp_path/'RevolandFBPoster'/'page-test')


def test_ctrl_c_waits_for_owned_child_then_returns_to_menu(monkeypatch):
    child = Mock()
    child.wait.side_effect = [KeyboardInterrupt, 0]
    monkeypatch.setattr('menu.subprocess.Popen', Mock(return_value=child))
    assert ToolMenu(say=lambda *args:None).cli('--server') == 0
    assert child.wait.call_count == 2
    child.terminate.assert_not_called()


@pytest.mark.parametrize('state', ['unknown', 'posted', 'submitting'])
def test_menu_never_resubmits_uncertain_or_posted_page_runs(tmp_path, monkeypatch, state):
    answers = iter(['3', '1'])
    menu = ToolMenu(ask=lambda _:next(answers), say=lambda *args:None)
    menu.data_dir = tmp_path
    folder = tmp_path/'data'/'page_tests'/('a'*32)
    folder.mkdir(parents=True)
    (folder/'run.json').write_text(json.dumps({'id':'a'*32,'status':state,'content':'Test',
        'page_name':'Fixture','page_url':'https://www.facebook.com/profile.php?id=123','images':[]}),encoding='utf-8')
    menu.cli = Mock()
    menu.page_test()
    menu.cli.assert_not_called()


def test_menu_only_submits_after_content_review_and_explicit_selection(tmp_path):
    answers = iter(['3','1','DANG'])
    menu = ToolMenu(ask=lambda _:next(answers), say=lambda *args:None)
    menu.data_dir = tmp_path
    folder = tmp_path/'data'/'page_tests'/('b'*32)
    folder.mkdir(parents=True)
    (folder/'run.json').write_text(json.dumps({'id':'b'*32,'status':'prepared','content':'Test',
        'page_name':'Fixture','page_url':'https://www.facebook.com/profile.php?id=123','images':[]}),encoding='utf-8')
    menu.cli = Mock()
    menu.page_test()
    menu.cli.assert_called_once_with('--page-test','--page-run','b'*32,'--submit-page-test')


def test_cancel_page_post_never_calls_cli(tmp_path):
    answers = iter(['3','1',''])
    menu = ToolMenu(ask=lambda _:next(answers), say=lambda *args:None)
    menu.page_runs = lambda:[{'id':'b'*32,'status':'prepared','content':'Test','images':[]}]
    menu.cli = Mock()
    menu.page_test()
    menu.cli.assert_not_called()


def test_customer_validation_does_not_overwrite_current_selection():
    menu = ToolMenu('khach01')
    with pytest.raises(ValueError): menu.set_customer('../other')
    assert menu.customer == 'khach01'
