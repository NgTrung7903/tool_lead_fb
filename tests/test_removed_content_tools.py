from fastapi.testclient import TestClient

from api import server


def test_removed_tools_are_unavailable_and_old_keys_stay_private():
    client = TestClient(server.app, headers={'X-Revoland-Client': 'local'})
    for path in ('/api/sources/text', '/api/content/paraphrase', '/api/content/rewrite-local', '/api/sources/folder'):
        assert client.post(path, json={'original': 'Nội dung', 'filename': 'bai.txt', 'text': 'Nội dung'}).status_code == 404
    html = client.get('/').text
    for marker in ('id="text-form"', 'id="rewrite"', 'id="rewrite-comparison"', 'id="folder-form"'):
        assert marker not in html
    assert 'id="json-form"' in html and 'id="content"' in html
    cfg = server.public_config({'paraphrase_api_key': 'legacy-secret', 'paraphrase_model': 'old-model'})
    assert not any(key.startswith('paraphrase') for key in cfg)
