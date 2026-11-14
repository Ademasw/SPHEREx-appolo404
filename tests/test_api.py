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


def test_stack_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.STACKS", tmp_path)
    client = TestClient(app)
    assert client.get("/api/stacks").json() == {"stacks": []}
    assert client.get("/api/stack/wise-0855/D6").status_code == 404
    folder = tmp_path / "wise-0855" / "D6"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text('{"frames": [{"index": 0}]}', encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (2, 2)).save(folder / "0.png")
    assert client.get("/api/stacks").json()["stacks"][0]["visits"] == 1
    assert client.get("/api/stack/wise-0855/D6").json()["frames"][0]["index"] == 0
    assert client.get("/api/stack/wise-0855/D6/frames/0").content.startswith(b"\x89PNG")
    assert client.get("/api/stack/wise-0855/D6/frames/1").status_code == 404
    # path parts are whitelisted
    assert client.get("/api/stack/unknown/D6").status_code == 404
    assert client.get("/api/stack/wise-0855/D7").status_code == 404


def test_comparison_missing_and_index_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.COMPARISON", tmp_path)
    client = TestClient(app)
    assert client.get("/api/comparison").status_code == 404
    assert client.get("/api/comparison/frames/2").status_code == 404
    (tmp_path / "manifest.json").write_text('{"frames": []}', encoding="utf-8")
    assert client.get("/api/comparison").json() == {"frames": []}
