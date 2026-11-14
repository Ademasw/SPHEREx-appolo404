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
