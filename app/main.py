import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI(title="Apollo 404 — SPHEREx", version="0.1.0")
PREVIEW = Path(__file__).resolve().parents[1] / "data" / "preview"


@app.get("/api/preview")
def preview():
    path = PREVIEW / "manifest.json"
    if not path.exists():
        raise HTTPException(404, "Preview not prepared; run scripts.prepare_preview")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/preview/frames/{index}")
def preview_frame(index: int):
    if index not in range(3):
        raise HTTPException(404, "Frame not found")
    path = PREVIEW / f"{index}.png"
    if not path.exists():
        raise HTTPException(404, "Preview not prepared")
    return FileResponse(path, media_type="image/png")


@app.get("/api/health")
def health():
    return {"status": "ok", "stage": "archive feasibility"}


@app.get("/api/targets")
def targets():
    # Names only: do not present unverified catalog positions as current coordinates.
    return {"targets": [
        {"id": "barnard", "name": "Barnard's Star"},
        {"id": "epsilon-indi-b", "name": "Epsilon Indi B"},
        {"id": "wise-0855", "name": "WISE 0855"},
        {"id": "rw-aur", "name": "RW Aurigae"},
        {"id": "r-dra", "name": "R Draconis"},
    ], "coordinate_status": "pending catalog and epoch verification"}
