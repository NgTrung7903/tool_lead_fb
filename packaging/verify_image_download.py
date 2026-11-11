"""Verify real image downloads through the packaged app, in an isolated runtime."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import requests
from PIL import Image
from io import BytesIO


def main():
    executable = Path(sys.argv[1]).resolve()
    source = Path(sys.argv[2]).resolve()
    fast = '--fast' in sys.argv[3:]
    rows = json.loads(source.read_text(encoding='utf-8-sig'))
    selected = [rows[i] for i in dict.fromkeys((0, len(rows) // 2, len(rows) - 1))]
    root = Path(__file__).resolve().parents[1]
    runtime = root / '.cache' / 'test-runs' / ('real-images-' + uuid.uuid4().hex)
    runtime.mkdir(parents=True)
    env = dict(os.environ, REVOLAND_DATA_DIR=str(runtime / 'customer'), REVOLAND_IMAGE_BROWSER='0')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    with (runtime / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([str(executable), '--no-browser', '--port', str(port)],
            env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with requests.Session() as session:
                session.trust_env = False
                base = f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 120
                while True:
                    try:
                        info = session.get(base + '/api/app-info', timeout=1)
                        info.raise_for_status()
                        break
                    except requests.RequestException:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError('EXE failed to start')
                        time.sleep(0.5)
                response = session.post(base + '/api/sources/json',
                    json={'filename': source.name, 'data': selected, 'defer_images': fast},
                    headers={'X-Revoland-Client': 'local'}, timeout=240)
                response.raise_for_status()
                imported = response.json()
                if fast:
                    assert all(row['pending_image_urls'] and not row['media_urls'] for row in imported)
                    for row in imported:
                        loaded = session.post(base + f"/api/sources/listings/{row['id']}/load-images",
                            headers={"X-Revoland-Client": "local"}, timeout=240)
                        loaded.raise_for_status()
                    imported = session.get(base + '/api/sources/listings', timeout=10).json()
                errors = [e for row in imported for e in row['image_errors']]
                count = 0
                for row in imported:
                    preview = session.get(base + f"/api/sources/listings/{row['id']}/preview", timeout=10).json()
                    for url in preview['media_urls']:
                        image = session.get(base + url, timeout=10)
                        image.raise_for_status()
                        with Image.open(BytesIO(image.content)) as decoded:
                            decoded.verify()
                        count += 1
                expected = sum(len(row['images']) for row in selected)
                catalog = session.get(base + '/api/sources/listings?summary=true&limit=2', timeout=10).json()
                assert len(catalog['items']) == 2 and catalog['total'] == len(imported)
                deleted = session.post(base + '/api/sources/listings/delete',
                    json={'ids': [row['id'] for row in imported]},
                    headers={'X-Revoland-Client': 'local'}, timeout=10)
                deleted.raise_for_status()
                assert deleted.json()['deleted'] == len(imported)
                assert session.get(base + '/api/sources/listings', timeout=10).json() == []
                report = {'build': info.json()['build_id'], 'mode': 'fast' if fast else 'eager', 'posts': len(imported),
                    'expected_images': expected, 'verified_images': count, 'errors': errors,
                    'passed': count == expected and not errors, 'logs': str(runtime)}
                (executable.parent / 'IMAGE_DOWNLOAD_VERIFICATION.json').write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
                return 0 if report['passed'] else 1
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                process.wait(timeout=20)


if __name__ == '__main__':
    raise SystemExit(main())
