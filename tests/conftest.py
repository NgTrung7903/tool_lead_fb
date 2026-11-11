"""Tests never touch customer config/session/history or call external services."""
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['REVOLAND_DATA_DIR'] = str(ROOT / '.cache' / 'test-runs' / uuid.uuid4().hex)

import pytest

# Never open the Cloudflare fallback browser window during tests.
os.environ['REVOLAND_IMAGE_BROWSER'] = '0'


@pytest.fixture(autouse=True)
def no_external_requests(monkeypatch):
    import requests
    def blocked(*args, **kwargs):
        raise AssertionError('Tests must mock external HTTP requests')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
