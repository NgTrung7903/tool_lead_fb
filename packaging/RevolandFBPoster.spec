# Build with: .venv\Scripts\python.exe -m PyInstaller packaging\RevolandFBPoster.spec
from pathlib import Path
import os
import ssl
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parent
browser = Path(os.environ['REVOLAND_BUILD_CHROMIUM']).resolve()
if not browser.is_dir() or not (browser / 'chrome-win64' / 'chrome.exe').is_file():
    raise RuntimeError('REVOLAND_BUILD_CHROMIUM must point to the installed Chromium revision folder.')

datas = [
    (str(root / 'api' / 'static'), 'api/static'),
    (str(root / 'core' / 'registry'), 'core/registry'),
    (str(root / 'examples'), 'examples'),
    (str(root / 'resources' / 'datasets'), 'resources/datasets'),
    (str(browser), 'bundled-browsers/' + browser.name),
]
# The bundled Python runtime loads this SSL trust-policy file next to ssl.py
# whenever an SSLContext is created. PyInstaller does not discover this data
# dependency automatically; omitting it breaks every HTTPS request.
runtime_ssl_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if runtime_ssl_policy.is_file():
    datas.append((str(runtime_ssl_policy), '.'))

datas += copy_metadata('uvicorn') + copy_metadata('fastapi') + copy_metadata('starlette')

a = Analysis([str(root / 'desktop_launcher.py')], pathex=[str(root)],
    binaries=[], datas=datas, hiddenimports=collect_submodules('uvicorn'),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'httpx', 'httpcore', 'IPython', 'tkinter'],
    noarchive=False, optimize=0)
pyz = PYZ(a.pure)
onedir = os.environ.get('REVOLAND_BUILD_ONEDIR') == '1'
exe = EXE(pyz, a.scripts, *([] if onedir else [a.binaries, a.datas]), [], name='CongCuBDS_JSON',
    exclude_binaries=onedir,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None)

if onedir:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CongCuBDS_JSON")
