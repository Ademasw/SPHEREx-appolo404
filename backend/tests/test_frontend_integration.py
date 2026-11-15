"""Verify both built frontends are served by the unchanged API application."""
from pathlib import Path
import re
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.skipif(not (Path(__file__).parents[1] / 'frontend/dist/index.html').exists(), reason='Build frontend first')
def test_both_frontends_and_assets_share_api_origin():
    client = TestClient(app)
    for path in ('/', '/legacy.html', '/dashboard', '/dashboard/advanced?q=Barnard&det=D3&fov=0.05', '/dashboard/player', '/dashboard/compare'):
        response = client.get(path)
        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', response.text):
            assert client.get(asset).status_code == 200
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/api/sequence').status_code == 400
    assert client.get('/api/not-a-real-endpoint').status_code == 404
