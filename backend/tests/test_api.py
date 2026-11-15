from fastapi.testclient import TestClient
from app.main import app


def test_health_and_targets():
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.get("/api/targets")
    assert response.status_code == 200
    assert len(response.json()["targets"]) == 5
    assert "pending" in response.json()["coordinate_status"]


def test_preview_missing_and_invalid_frames(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.PREVIEW", tmp_path)
    client = TestClient(app)
    assert client.get("/api/preview").status_code == 404
    assert client.get("/api/preview/frames/0").status_code == 404
    assert client.get("/api/preview/frames/-1").status_code == 404
    assert client.get("/api/preview/frames/3").status_code == 404


def test_prepared_preview_can_be_served(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.PREVIEW", tmp_path)
    (tmp_path / "manifest.json").write_text('{"frames": [{"index": 0}]}', encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (2, 2)).save(tmp_path / "0.png")
    client = TestClient(app)
    assert client.get("/api/preview").json()["frames"][0]["index"] == 0
    response = client.get("/api/preview/frames/0")
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_sequence_reports_progress_then_result(monkeypatch):
    calls = []

    def fake_request(ra, dec, detector, fov, target=None, background="model"):
        calls.append((ra, dec, detector, fov))
        return {"status": "running", "stage": "downloading", "done": 3, "total": 40,
                "elapsed_s": 1.0, "error": None} if len(calls) == 1 else {"status": "done", "manifest": {"frames": []}}

    monkeypatch.setattr("app.main.jobs.request", fake_request)
    client = TestClient(app)
    first = client.get("/api/sequence", params={"ra": 133.75976527, "dec": -7.24218218, "det": "D6"})
    assert first.status_code == 202
    assert first.json()["stage"] == "downloading"
    assert calls[0] == (133.7598, -7.2422, "D6", 0.1)  # position rounded for caching
    second = client.get("/api/sequence", params={"q": "133.75976527 -7.24218218"})
    assert second.status_code == 200 and second.json()["manifest"] == {"frames": [], "target": None}


def test_sequence_validates_input():
    client = TestClient(app)
    assert client.get("/api/sequence", params={"ra": 400, "dec": 0}).status_code == 400
    assert client.get("/api/sequence", params={"ra": 10, "dec": 0, "det": "D9"}).status_code == 400
    assert client.get("/api/sequence", params={"ra": 10, "dec": 0, "fov": 5}).status_code == 400
    assert client.get("/api/sequence").status_code == 400
    assert client.get("/api/sequence/../../etc/D6/frames/0.png").status_code == 404
    assert client.get("/api/sequence/10.0000_+0.0000_0.1/D6/other/0.png").status_code == 404
    assert client.get("/api/sequence/10.0000_+0.0000_0.1/D6/manifest.json").status_code == 404


def test_comparison_missing_and_index_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.COMPARISON", tmp_path)
    client = TestClient(app)
    assert client.get("/api/comparison").status_code == 404
    assert client.get("/api/comparison/frames/2").status_code == 404
    (tmp_path / "manifest.json").write_text('{"frames": []}', encoding="utf-8")
    assert client.get("/api/comparison").json() == {"frames": []}


def test_barnard_inspection_missing_and_prepared(tmp_path, monkeypatch):
    monkeypatch.setattr('app.main.BARNARD', tmp_path)
    client = TestClient(app)
    assert client.get('/api/barnard').status_code == 404
    assert client.get('/api/barnard/frames/2').status_code == 404
    (tmp_path/'manifest.json').write_text('{"target_name":"Barnard","warnings":["Core flagged"]}',encoding='utf-8')
    data = client.get('/api/barnard').json()
    assert data['warnings'] == ['Core flagged']


def test_epsilon_comparison_keeps_science_warnings(tmp_path, monkeypatch):
    monkeypatch.setattr('app.main.EPSILON',tmp_path)
    client=TestClient(app)
    assert client.get('/api/epsilon').status_code==404
    assert client.get('/api/epsilon/frames/2').status_code==404
    (tmp_path/'manifest.json').write_text('{"warnings":["Motion unconfirmed"]}',encoding='utf-8')
    assert client.get('/api/epsilon').json()['warnings']==['Motion unconfirmed']
    from PIL import Image
    Image.new('RGB',(2,2),(10,10,10)).save(tmp_path/'0.png')
    Image.new('RGB',(2,2),(255,166,64)).save(tmp_path/'0-mask.png')
    assert client.get('/api/epsilon/frames/0').content==(tmp_path/'0.png').read_bytes()
    assert client.get('/api/epsilon/frames/0?mask=true').content==(tmp_path/'0-mask.png').read_bytes()


def test_motion_report_preserves_preliminary_status(tmp_path,monkeypatch):
    monkeypatch.setattr('app.main.EPSILON',tmp_path)
    client=TestClient(app)
    assert client.get('/api/epsilon/motion').status_code==404
    (tmp_path/'motion-report.json').write_text('{"status":"exploratory_not_confirmed"}',encoding='utf-8')
    assert client.get('/api/epsilon/motion').json()['status']=='exploratory_not_confirmed'


def test_pair_difference_of_any_two_visits(tmp_path, monkeypatch):
    import numpy as np
    from app import pipeline
    monkeypatch.setattr(pipeline, "SEQUENCES", tmp_path)
    folder = tmp_path / "10.0000_+0.0000_0.1" / "D6" / "visits"
    folder.mkdir(parents=True)
    for i, level in enumerate((1.0, 2.0, 5.0)):
        np.savez_compressed(folder / f"{i}.npz", stack=np.full((10, 10), level, dtype=np.float32),
                            saturated=np.zeros((10, 10), dtype=bool))
    client = TestClient(app)
    response = client.get("/api/sequence/10.0000_+0.0000_0.1/D6/pair/0/2.png")
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert (tmp_path / "10.0000_+0.0000_0.1" / "D6" / "pairs" / "0-2.png").exists()
    assert client.get("/api/sequence/10.0000_+0.0000_0.1/D6/pair/1/1.png").status_code == 404
    assert client.get("/api/sequence/10.0000_+0.0000_0.1/D6/pair/0/7.png").status_code == 404
    assert client.get("/api/sequence/bad/D6/pair/0/1.png").status_code == 404


def test_cached_target_is_not_reused_for_coordinate_request(monkeypatch):
    cached = {'target': {'name':'Wrong target'}, 'frames':[{'time_utc':'2025-01-01T00:00:00','predicted_position':{'x':1},'photometry':{'flux':123}}]}
    def request(*args, **kwargs):
        assert kwargs['target'] is None
        return {'status':'done','manifest':cached}
    monkeypatch.setattr('app.main.jobs.request',request)
    response=TestClient(app).get('/api/sequence?ra=10&dec=0').json()['manifest']
    assert response['target'] is None
    assert response['frames'][0]['predicted_position'] is None
    assert 'photometry' not in response['frames'][0]
    assert cached['target']['name']=='Wrong target'
    assert cached['frames'][0]['photometry']['flux']==123
