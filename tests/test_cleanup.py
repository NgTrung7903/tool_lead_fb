"""Exercise deletion only inside a throwaway project, never the real workspace."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def cleanup_project(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell or os.name != 'nt':
        pytest.skip('Windows PowerShell cleanup script')
    project = tmp_path / 'project'
    (project / 'scripts').mkdir(parents=True)
    script = project / 'scripts' / 'clean_project.ps1'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts' / script.name, script)
    (project / 'desktop_launcher.py').write_text('# fixture', encoding='utf-8')
    def run(*args):
        return subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), *args],
                              capture_output=True, text=True, timeout=30)
    return project, run


def put(project, name):
    path = project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('keep or regenerate', encoding='utf-8')
    return path


def test_preview_then_cleanup_keeps_customer_data_and_current_exe(cleanup_project):
    project, run = cleanup_project
    generated = [put(project, name) for name in (
        '.cache/pytest/result.txt', '.cache/build-current/result.txt',
        'build/temp.txt', 'services/__pycache__/test.pyc',
        '.pytest-old/result.txt', '.test-runs/result.txt',
        'dist/folder-posting/FacebookLeadFilter.exe', 'dist/RevolandFBPoster.exe', 'dist/SHA256.txt',
        'dist/customer-preview-v15/CongCuBDS_JSON.exe', 'dist/customer-group-column-v16/CongCuBDS_JSON.exe', 'dist/company-handover-v17/CongCuBDS_JSON.exe')]
    preserved = [put(project, name) for name in (
        'data/customer.sqlite3', 'profiles/cookie', 'browser_data/session', 'config/config.json',
        'config/groups.json', '.venv/python.exe', 'dist/FacebookLeadFilter.exe',
        'dist/revoland-link-v18/CongCuBDS_JSON.exe',
        'resources/datasets/quinland.json')]
    preview = run('-OldReleases')
    assert preview.returncode == 0, preview.stderr
    assert 'Preview only' in preview.stdout
    assert all(path.exists() for path in generated + preserved)
    applied = run('-Apply', '-OldReleases')
    assert applied.returncode == 0, applied.stderr
    assert all(not path.exists() for path in generated)
    assert all(path.exists() for path in preserved)


def test_unrecognized_release_stops_before_any_deletion(cleanup_project):
    project, run = cleanup_project
    important = put(project, 'dist/folder-posting/customer-notes.txt')
    generated = put(project, 'build/temp.txt')
    result = run('-Apply', '-OldReleases')
    assert result.returncode != 0
    assert important.exists() and generated.exists()


def test_cleanup_refuses_parent_symlink(cleanup_project, tmp_path):
    project, run = cleanup_project
    outside = tmp_path / 'outside'
    marker = put(outside, 'pytest/customer.txt')
    try:
        os.symlink(outside, project / '.cache', target_is_directory=True)
    except OSError:
        # Windows junctions do not need the symlink privilege on ordinary local disks.
        helper = tmp_path / 'make-junction.ps1'
        helper.write_text('param([string]$Link, [string]$Target)\n'
                          'New-Item -ItemType Junction -Path $Link -Target $Target -ErrorAction Stop | Out-Null',
                          encoding='utf-8')
        made = subprocess.run([shutil.which('pwsh') or shutil.which('powershell'), '-NoProfile',
                               '-ExecutionPolicy', 'Bypass', '-File', str(helper),
                               str(project / '.cache'), str(outside)], capture_output=True, timeout=30)
        if made.returncode != 0:
            pytest.skip('This filesystem cannot create directory symlinks or junctions')
    try:
        result = run('-Apply')
        assert result.returncode != 0
        assert 'reparse point' in result.stderr
        assert marker.exists()
    finally:
        # Remove only the link so the real project's cleaner can delete this fixture later.
        os.rmdir(project / '.cache')


