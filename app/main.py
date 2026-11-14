import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.targets import TARGETS

app = FastAPI(title="Apollo 404 — SPHEREx", version="0.1.0")
PREVIEW = Path(__file__).resolve().parents[1] / "data" / "preview"
COMPARISON = Path(__file__).resolve().parents[1] / "data" / "comparison"
STACKS = Path(__file__).resolve().parents[1] / "data" / "stacks"
TARGET_IDS = {target["id"] for target in TARGETS}
DETECTORS = {f"D{i}" for i in range(1, 7)}


def stack_dir(target: str, detector: str) -> Path:
    # Whitelist both path parts: they come from the URL.
    if target not in TARGET_IDS or detector not in DETECTORS:
        raise HTTPException(404, "Unknown target or detector")
    return STACKS / target / detector


@app.get("/api/stacks")
def stacks():
    """Prepared visit stacks, so the viewer can offer only what exists."""
    available = []
    for target in TARGETS:
        for detector in sorted(DETECTORS):
            path = STACKS / target["id"] / detector / "manifest.json"
            if path.exists():
                manifest = json.loads(path.read_text(encoding="utf-8"))
                available.append({"target": target["id"], "name": target["name"], "detector": detector,
                                  "visits": len(manifest["frames"])})
    return {"stacks": available}


@app.get("/api/stack/{target}/{detector}")
def stack(target: str, detector: str):
    path = stack_dir(target, detector) / "manifest.json"
    if not path.exists():
        raise HTTPException(404, "Stack not prepared; run scripts.prepare_stack")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/stack/{target}/{detector}/frames/{index}")
def stack_frame(target: str, detector: str, index: int):
    path = stack_dir(target, detector) / f"{index}.png"
    if index < 0 or not path.exists():
        raise HTTPException(404, "Frame not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/stack/{target}/{detector}/difference")
def stack_difference(target: str, detector: str):
    path = stack_dir(target, detector) / "difference.png"
    if not path.exists():
        raise HTTPException(404, "Difference not prepared")
    return FileResponse(path, media_type="image/png")


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
