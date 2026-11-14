import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.targets import TARGETS

app = FastAPI(title="Apollo 404 — SPHEREx", version="0.1.0")
PREVIEW = Path(__file__).resolve().parents[1] / "data" / "preview"
COMPARISON = Path(__file__).resolve().parents[1] / "data" / "comparison"


@app.get("/api/comparison")
def comparison():
    path = COMPARISON / "manifest.json"
    if not path.exists():
        raise HTTPException(404, "Comparison not prepared; run scripts.prepare_blink")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/comparison/frames/{index}")
def comparison_frame(index: int):
    if index not in range(2):
        raise HTTPException(404, "Frame not found")
    path = COMPARISON / f"{index}.png"
    if not path.exists():
        raise HTTPException(404, "Comparison not prepared")
    return FileResponse(path, media_type="image/png")


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
    return {"targets": TARGETS, "coordinate_status": "pending catalog and epoch verification"}


# Build before starting FastAPI to serve UI and API from the same origin.
FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
