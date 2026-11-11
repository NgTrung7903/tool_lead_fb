from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from api import server
from models.schema import PropertyListing
from services.revoland_service import SAMPLE_LISTINGS, RevolandAPIError


@pytest.fixture
def client():
    return TestClient(server.app, headers={'X-Revoland-Client':'local'})


def test_dashboard_and_javascript(client):
    assert client.get('/').status_code == 200
    script = client.get('/assets/app.js')
    assert script.status_code == 200 and 'scheduleCampaignPoll' in script.text


def test_config_never_returns_key(client):
    response = client.get('/api/config')
    assert response.status_code == 200
    assert 'revoland_api_key' not in response.json()
    assert response.headers['Cache-Control'] == 'no-store'


def test_mutations_require_header_and_same_origin(client):
    raw = TestClient(server.app)
    assert raw.post('/api/session/logout').status_code == 403
    assert client.post('/api/session/logout', headers={'Origin':'https://evil.test'}).status_code == 403


def test_config_delay_validation(client):
    assert client.post('/api/config',json={'min_delay_seconds':10,'max_delay_seconds':2}).status_code == 400


def test_api_errors_are_explicit(client, monkeypatch):
    monkeypatch.setattr(server.revoland_service,'get_listings',Mock(side_effect=RevolandAPIError('HTTP 401')))
    response = client.get('/api/revoland/listings')
    assert response.status_code == 502
    assert '401' in response.json()['detail']


def test_manual_resolution_requires_confirmation(client):
    assert client.post('/api/campaigns/fake/tasks/fake/resolve',json={'outcome':'not_submitted'}).status_code == 400


def test_preview_has_fingerprint_and_creation_requires_it(client, monkeypatch):
    listing = PropertyListing(**SAMPLE_LISTINGS[0])
    monkeypatch.setattr(server.revoland_service,'get_listing_by_id',Mock(return_value=listing))
    response = client.get('/api/revoland/listings/a/preview')
    assert response.status_code == 200
    assert len(response.json()['preview_token']) == 64
    assert client.post('/api/campaigns/create',json={'listing_id':'a','target_group_ids':['g']}).status_code == 422
