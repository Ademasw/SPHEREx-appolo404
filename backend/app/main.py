import json
import math
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app import pipeline
from app.jobs import JobManager
from app.resolve import ResolveError, resolve
from app.targets import TARGETS
from app.cloud_jobs import router as cloud_jobs_router
from app.science import COLOUR_PAIRS, matched_difference, matched_range, spectrum, visit_quality, colour_composite
from app.moving import archive_matches, horizons_ephemeris
from app.gaia import match as gaia_match

app = FastAPI(title="Apollo 404 — SPHEREx", version="0.1.0")
app.include_router(cloud_jobs_router)  # teammate's cloud-based /api/jobs search
PREVIEW = Path(__file__).resolve().parents[1] / "data" / "preview"
COMPARISON = Path(__file__).resolve().parents[1] / "data" / "comparison"
SEQUENCE_KEY = re.compile(r"^\d{1,3}\.\d{4}_[+-]\d{1,2}\.\d{4}_0\.\d+(_med|_raw)?(_clean)?(_nearest)?(_v[a-f0-9]{12})?$")
jobs = JobManager()


def _position_from(q, ra, dec):
    """Resolve the request into a rounded position and optional catalog target."""
    if q:
        try:
            info = resolve(q)
        except ResolveError as error:
            raise HTTPException(404, str(error))
    elif ra is not None and dec is not None:
        if not (math.isfinite(ra) and math.isfinite(dec) and 0 <= ra < 360 and -90 <= dec <= 90):
            raise HTTPException(400, "RA must be in [0, 360) and Dec in [-90, 90] degrees")
        info = {"name": None, "ra_deg": ra, "dec_deg": dec, "source": "coordinates"}
    else:
        raise HTTPException(400, "Give q (name or coordinates) or ra and dec")
    info["ra_deg"], info["dec_deg"] = round(info["ra_deg"], 4) % 360, round(info["dec_deg"], 4)
    return info


def _motion_target(info, epoch=2026.0):
    """Prefer a confident Gaia DR3 linear-motion solution, else SIMBAD."""
    # Named targets already carry an object identity from SIMBAD. Avoid a
    # blocking remote cone search for arbitrary coordinate clicks; callers can
    # use /api/gaia explicitly when they want a Gaia overlay at raw coords.
    if not info.get("name"):
        return info
    try:
        gaia = gaia_match(info["ra_deg"], info["dec_deg"], epoch)
    except Exception:
        gaia = None
    if gaia:
        info = {**info, "gaia": gaia}
        if gaia.get("quality_ok"):
            return {**info, "ra2000": gaia["ra_deg"], "dec2000": gaia["dec_deg"],
                    "pmra": gaia["pmra_mas_yr"], "pmdec": gaia["pmdec_mas_yr"],
                    "motion_epoch": gaia.get("ref_epoch") or 2016.0,
                    "motion_source": "Gaia DR3"}
    return info


@app.get("/api/resolve")
def resolve_endpoint(q: str):
    info = _position_from(q, None, None)
    info["gaia"] = gaia_match(info["ra_deg"], info["dec_deg"])
    return info


@app.get("/api/gaia")
def gaia_endpoint(ra: float, dec: float, epoch: float = 2026.0):
    if not (math.isfinite(ra) and math.isfinite(dec) and 0 <= ra < 360 and -90 <= dec <= 90):
        raise HTTPException(400, "RA and Dec are invalid")
    return {"query": {"ra_deg": ra, "dec_deg": dec, "epoch": epoch}, "source": "Gaia DR3", "match": gaia_match(ra, dec, epoch)}


@app.get("/api/sequence")
def sequence(response: Response, q: str | None = None, ra: float | None = None, dec: float | None = None,
             det: str = "D6", fov: float = 0.1, bg: str = "model", clean: bool = False, smooth: bool = True,
             refresh: bool = False):
    """Frames and visit stacks for any position. 202 with progress while processing."""
    if det not in pipeline.DETECTORS:
        raise HTTPException(400, "det must be D1 to D6")
    if fov not in pipeline.FOVS:
        raise HTTPException(400, f"fov must be one of {list(pipeline.FOVS)}")
    if bg not in pipeline.BACKGROUNDS:
        raise HTTPException(400, f"bg must be one of {list(pipeline.BACKGROUNDS)}")
    info = _position_from(q, ra, dec)
    target = _motion_target(info)
    if target.get("pmra") is None or target.get("pmdec") is None:
        target = None
    request_args = {"target": target, "background": bg}
    if clean:
        request_args["clean"] = True
    if not smooth:
        request_args["smooth"] = False
    if refresh:
        request_args["refresh"] = True
    state = jobs.request(info["ra_deg"], info["dec_deg"], det, fov, **request_args)
    state["resolved"] = info
    if state["status"] == "error":
        response.status_code = 502
    elif state["status"] != "done":
        response.status_code = 202
    return state


@app.post("/api/sequence/refresh")
def refresh_sequence(response: Response, q: str | None = None, ra: float | None = None,
                     dec: float | None = None, det: str = "D6", fov: float = 0.1,
                     bg: str = "model", clean: bool = False, smooth: bool = True):
    return sequence(response, q, ra, dec, det, fov, bg, clean, smooth, refresh=True)


@app.get("/api/sequence/{key}/{det}/{kind}/{index}.png")
def sequence_image(key: str, det: str, kind: str, index: int):
    if not SEQUENCE_KEY.match(key) or det not in pipeline.DETECTORS or kind not in ("frames", "visits", "masks") or index < 0:
        raise HTTPException(404, "Not found")
    path = pipeline.product_dir(key, det) / kind / f"{index}.png"
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/sequence/{key}/{det}/pair/{a}/{b}.png")
def sequence_pair(key: str, det: str, a: int, b: int):
    """Difference of any two visits (b minus a), rendered on first request."""
    if not SEQUENCE_KEY.match(key) or det not in pipeline.DETECTORS or not (0 <= a < 16 and 0 <= b < 16):
        raise HTTPException(404, "Not found")
    path = pipeline.pair_difference(key, det, a, b)
    if path is None:
        raise HTTPException(404, "Visits not available for comparison; recompute this position")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/sequence/{key}/{det}/matched/{a}/{b}.png")
def sequence_matched(key: str, det: str, a: int, b: int):
    if not SEQUENCE_KEY.match(key) or det not in pipeline.DETECTORS or not (0 <= a < 16 and 0 <= b < 16):
        raise HTTPException(404, "Not found")
    path = pipeline.product_dir(key, det) / "pairs" / f"matched-{a}-{b}.png"
    if not path.exists():
        raise HTTPException(404, "Request the matched comparison product first")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/sequence/{key}/{det}/{name}")
def sequence_file(key: str, det: str, name: str):
    files = {"difference.png": "image/png", "blink.gif": "image/gif"}
    if not SEQUENCE_KEY.match(key) or det not in pipeline.DETECTORS or name not in files:
        raise HTTPException(404, "Not found")
    path = pipeline.product_dir(key, det) / name
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type=files[name], headers={"Cache-Control": "public, max-age=86400"})


def _manifest(key, det):
    if not SEQUENCE_KEY.match(key) or det not in pipeline.DETECTORS:
        raise HTTPException(404, "Not found")
    path = pipeline.SEQUENCES / key / det / "manifest.json"
    if not path.exists():
        raise HTTPException(404, "Detector sequence is not prepared")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/science/{key}/quality")
def science_quality(key: str, det: str = "D6"):
    manifest = _manifest(key, det)
    return {"detector": det, "visits": [{**visit_quality(v), "index": i}
                                         for i, v in enumerate(manifest.get("visits", []))]}


@app.get("/api/science/{key}/matched")
def science_matched(key: str, det: str = "D6", a: int = 0, b: int = 1):
    manifest = _manifest(key, det)
    visits = manifest.get("visits", [])
    if a < 0 or b < 0 or a >= len(visits) or b >= len(visits) or a == b:
        raise HTTPException(404, "Visits are not available for wavelength matching")
    common = matched_range(visits[a], visits[b])
    if common is None:
        raise HTTPException(422, "The selected visits have no shared wavelength range")
    folder = pipeline.product_dir(key, det)
    output = folder / "pairs" / f"matched-{a}-{b}.png"
    product = matched_difference(folder, manifest, a, b, output)
    if product is None:
        raise HTTPException(422, "Matching wavelength frames are not available for both visits")
    return {"detector": det, "visit_a": a, "visit_b": b, "shared_wavelength": common,
            "difference_url": f"/api/sequence/{key}/{det}/matched/{a}/{b}.png",
            "frames_used": {"a": product["frames_a"], "b": product["frames_b"]},
            "method": "only frames inside the shared wavelength interval were stacked before subtraction"}


@app.get("/api/science/{key}/spectrum")
def science_spectrum(key: str):
    if not SEQUENCE_KEY.fullmatch(key):
        raise HTTPException(404, "Not found")
    manifests = [_manifest(key, det) for det in pipeline.DETECTORS
                 if (pipeline.SEQUENCES / key / det / "manifest.json").exists()]
    if not manifests:
        raise HTTPException(404, "No prepared detector sequences")
    return {"points": spectrum(manifests), "detectors": [m["query"]["detector"] for m in manifests],
            "note": "flux is a simple variance-weighted aperture sum; this is an exploratory spectrum, not calibrated flux"}


@app.get("/api/science/{key}/colour/{visit}.png")
def science_colour(key: str, visit: int):
    if not SEQUENCE_KEY.fullmatch(key) or visit < 0:
        raise HTTPException(404, "Not found")
    manifests = {det: _manifest(key, det) for det in pipeline.DETECTORS
                 if (pipeline.SEQUENCES / key / det / "manifest.json").exists()}
    output = pipeline.SEQUENCES / key / "colour" / f"{visit}.png"
    result = colour_composite(pipeline.SEQUENCES / key, manifests, visit, output)
    if result is None:
        raise HTTPException(404, "All six detector visits are required for this colour composite")
    return FileResponse(output, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/moving/ephemeris")
def moving_ephemeris(target: str = "C/2025 N1", start: str = "2025-12-08T00:00:00Z",
                    stop: str = "2025-12-16T00:00:00Z", step: str = "1h"):
    try:
        points = horizons_ephemeris(target, start, stop, step)
    except RuntimeError as error:
        raise HTTPException(502, str(error))
    return {"target": target, "frame": "geocentric", "points": points,
            "note": "positions are from JPL Horizons; archive matching is still an explicit next request"}


@app.get("/api/moving/coverage")
def moving_coverage(target: str = "C/2025 N1", start: str = "2025-12-08T00:00:00Z",
                    stop: str = "2025-12-16T00:00:00Z", step: str = "1d", release: str = "dr1"):
    if release not in {"dr1", "qr3"}:
        raise HTTPException(400, "release must be dr1 or qr3")
    try:
        points = horizons_ephemeris(target, start, stop, step)
        matches = archive_matches(points, release)
    except RuntimeError as error:
        raise HTTPException(502, str(error))
    return {"target": target, "release": release, "matches": matches,
            "note": "coverage probes are centered on each Horizons position; frame-specific cutout processing is required before photometry"}


BARNARD = Path(__file__).resolve().parents[1] / "data" / "barnard"
EPSILON = Path(__file__).resolve().parents[1] / 'data' / 'epsilon-cloud'


@app.get('/api/epsilon/motion')
def epsilon_motion():
    path=EPSILON/'motion-report.json'
    if not path.exists():
        raise HTTPException(404,'Motion experiment not prepared; run scripts.measure_epsilon')
    return json.loads(path.read_text(encoding='utf-8'))


@app.get('/api/epsilon')
def epsilon():
    path = EPSILON / 'manifest.json'
    if not path.exists():
        raise HTTPException(404, 'Epsilon Indi B comparison is not prepared')
    return json.loads(path.read_text(encoding='utf-8'))


@app.get('/api/epsilon/frames/{index}')
def epsilon_frame(index: int, mask: bool=False):
    if index not in range(2):
        raise HTTPException(404, 'Frame not found')
    path = EPSILON / f'{index}{"-mask" if mask else ""}.png'
    if not path.exists():
        raise HTTPException(404, 'Epsilon Indi B comparison is not prepared')
    return FileResponse(path,media_type='image/png')


@app.get('/api/barnard')
def barnard():
    path = BARNARD / 'manifest.json'
    if not path.exists():
        raise HTTPException(404, 'Barnard source inspection is not prepared')
    return json.loads(path.read_text(encoding='utf-8'))


@app.get('/api/barnard/frames/{index}')
def barnard_frame(index: int):
    if index not in range(2):
        raise HTTPException(404, 'Frame not found')
    path = BARNARD / f'{index}.png'
    if not path.exists():
        raise HTTPException(404, 'Barnard source inspection is not prepared')
    return FileResponse(path, media_type='image/png')


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
    @app.get("/dashboard", include_in_schema=False)
    @app.get("/dashboard/advanced", include_in_schema=False)
    @app.get("/dashboard/player", include_in_schema=False)
    @app.get("/dashboard/compare", include_in_schema=False)
    @app.get("/dashboard/colour", include_in_schema=False)
    def dashboard_page():
        return FileResponse(FRONTEND / "index.html", media_type="text/html")

    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
