import time
from fastapi.testclient import TestClient
from app.main import app
from app import cloud_jobs as jobs


def test_query_validation_and_unknown_job():
    client=TestClient(app)
    assert client.post('/api/jobs',json={'ra':360,'dec':0}).status_code==422
    assert client.post('/api/jobs',json={'ra':1,'dec':-91}).status_code==422
    assert client.post('/api/jobs',json={'ra':1,'dec':0,'fov_deg':1}).status_code==422
    assert client.get('/api/jobs/not-a-job').status_code==404


def test_empty_real_search_fails_without_generating_frames(tmp_path,monkeypatch):
    monkeypatch.setattr(jobs,'DIRECTORY',tmp_path)
    monkeypatch.setattr(jobs,'search',lambda *args:{'observations':[]})
    client=TestClient(app)
    response=client.post('/api/jobs',json={'ra':1,'dec':1})
    assert response.status_code==200
    ident=response.json()['job_id']
    for _ in range(100):
        state=client.get('/api/jobs/'+ident).json()
        if state['status']=='failed':break
        time.sleep(.01)
    assert state['status']=='failed'
    assert 'No cloud-accessible' in state['message']
    assert client.get(f'/api/jobs/{ident}/result').status_code==404
    assert not list(tmp_path.rglob('*.png'))
