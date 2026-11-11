from pathlib import Path
import sys

import pytest

from desktop_launcher import configure_runtime


def test_launcher_uses_persistent_customer_storage(tmp_path, monkeypatch):
    monkeypatch.delenv('REVOLAND_DATA_DIR', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    runtime = configure_runtime('khach01')
    assert runtime == tmp_path / 'RevolandFBPoster' / 'khach01'
    assert runtime.is_dir()


@pytest.mark.parametrize('customer',['../other','', 'name with spaces', 'x'*49])
def test_launcher_rejects_invalid_customer(customer):
    with pytest.raises(ValueError): configure_runtime(customer)


def test_frozen_browser_resources_do_not_own_customer_data(tmp_path, monkeypatch):
    assets = tmp_path / 'unpacked'
    data = tmp_path / 'persistent'
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(assets), raising=False)
    monkeypatch.setenv('REVOLAND_DATA_DIR', str(data))
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', 'old-value')
    assert configure_runtime('default') == data
    import os
    assert Path(os.environ['PLAYWRIGHT_BROWSERS_PATH']) == assets / 'bundled-browsers'


def test_launcher_falls_back_to_next_free_port_when_preferred_is_busy():
    import socket
    from desktop_launcher import bind_first_free_port
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen(1)
        busy_port = occupied.getsockname()[1]
        listener, chosen = bind_first_free_port(busy_port, attempts=10)
        try:
            assert chosen > busy_port
        finally:
            listener.close()


def test_reopen_running_dashboard_opens_saved_local_url(tmp_path, monkeypatch):
    from desktop_launcher import reopen_running_dashboard
    from build_info import BUILD_ID
    monkeypatch.setattr('desktop_launcher.running_dashboard_build', lambda url: BUILD_ID)
    opened = []
    monkeypatch.setattr('desktop_launcher.webbrowser.open', opened.append)
    assert not reopen_running_dashboard(tmp_path)
    (tmp_path / 'dashboard.url').write_text('https://evil.test:8000', encoding='utf-8')
    assert not reopen_running_dashboard(tmp_path)
    (tmp_path / 'dashboard.url').write_text('http://127.0.0.1:8012', encoding='utf-8')
    assert reopen_running_dashboard(tmp_path)
    assert opened == ['http://127.0.0.1:8012']


@pytest.mark.parametrize('build', [None, 'old-build'])
def test_new_launcher_does_not_reopen_an_old_dashboard(tmp_path, monkeypatch, build):
    from desktop_launcher import reopen_running_dashboard
    opened = []
    monkeypatch.setattr('desktop_launcher.webbrowser.open', opened.append)
    monkeypatch.setattr('desktop_launcher.running_dashboard_build', lambda url: build)
    (tmp_path / 'dashboard.url').write_text('http://127.0.0.1:8000', encoding='utf-8')
    with pytest.raises(ValueError, match='tool cũ'):
        reopen_running_dashboard(tmp_path)
    assert not opened
