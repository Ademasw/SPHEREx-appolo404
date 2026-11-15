"""On-demand pipeline: any sky position -> SPHEREx frame series and visit stacks.

Nothing is downloaded in advance. For a requested RA/Dec, detector and field
of view the pipeline

1. asks IRSA which SPHEREx images cover the position (DR1 + QR3 via SIA),
2. downloads only the image part of each cutout (see fastfits; ~120 KB
   instead of ~4 MB per frame), in parallel, with retries,
3. aligns every frame on one fixed sky grid, subtracts the ZODI model and the
   sky level, masks unusable pixels,
4. groups frames into visits (SPHEREx returns about every six months) and
   stacks each visit,
5. renders PNGs (every frame, every visit, last-minus-first difference) and a
   manifest.json that the API and viewer use.

Results are cached on disk, so a position is processed once.
"""
import hashlib
import json
import os
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import astropy.units as u
import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS, FITSFixedWarning
from astroquery.ipac.irsa import Irsa
from PIL import Image, ImageDraw

from app.astrometry import propagate
from app.cloudfits import cloud_url as parse_cloud_url, fetch_section
from app.fastfits import fetch_prefix
from app.preview import make_grid, unusable_mask
from app.stack import align_bilinear, aperture_photometry, combine, group_epochs, measure_source, subtract_background

warnings.simplefilter("ignore", FITSFixedWarning)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEQUENCES = DATA / "sequences"
CUTOUTS = DATA / "cutouts_fast"
METADATA = DATA / "metadata_live"
WAVETABLES = Path(__file__).resolve().parent / "wavetables"

# The deep products are official SPHEREx collections and are especially useful
# near the ecliptic poles.  Keep them in the same archive query so a normal
# search can use them without a separate code path.
COLLECTIONS = ("spherex_dr1", "spherex_qr3", "spherex_dr1_deep", "spherex_qr3_deep")
DETECTORS = tuple(f"D{i}" for i in range(1, 7))
FOVS = (0.05, 0.1, 0.2)
MAX_PER_VISIT = 16  # enough for a clean stack; keeps downloads short
DOWNLOAD_BUDGET_S = 40  # then continue with what arrived; a later request can top up
MIN_VISIT_FRAMES = 5
WORKERS = 8
METADATA_TTL_S = 24 * 3600
SEARCH_TIMEOUT_S = 30
_SEARCH_POOL = ThreadPoolExecutor(4)  # a hung search thread is abandoned, not waited for
# 'auto': IRSA cutout first, public cloud copy on failure; 'cloud': cloud only
# (use if the cutout service is down, e.g. SPHEREX_SOURCE=cloud).
SOURCE = os.environ.get("SPHEREX_SOURCE", "auto").lower()
INVALID_RGB = (45, 35, 55)


def log(message):
    print(f"[pipeline] {message}", flush=True)


class PipelineError(Exception):
    """Expected failure with a message that can be shown to users."""


# How the sky background is removed. 'model' (default): the ZODI model shipped in
# each SPHEREx file, then the residual sky level. 'median': only the local sky
# level (sigma-clipped median). 'none': raw calibrated sky, nothing removed.
BACKGROUNDS = ("model", "median", "none")
_BG_SUFFIX = {"model": "", "median": "_med", "none": "_raw"}


def sequence_key(ra, dec, fov, background="model", clean=False, smooth=True):
    return f"{ra:.4f}_{dec:+.4f}_{fov:g}" + _BG_SUFFIX[background] + ("_clean" if clean else "") + ("_nearest" if not smooth else "")


def output_dir(ra, dec, detector, fov, background="model", clean=False, smooth=True):
    return SEQUENCES / sequence_key(ra, dec, fov, background, clean, smooth) / detector


# --------------------------------------------------------------------------- archive

def query_observations(ra, dec):
    """All SPHEREx images covering the position (every detector), cached for a day."""
    METADATA.mkdir(parents=True, exist_ok=True)
    path = METADATA / f"{ra:.4f}_{dec:+.4f}.json"
    if path.exists() and time.time() - path.stat().st_mtime < METADATA_TTL_S:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if all("cloud_url" in o for o in cached["observations"]):
            return cached
    # Normally ~4 s. Under load a request can hang indefinitely (the astroquery
    # timeout does not reach the SIA call), so each attempt runs in a helper
    # thread with a hard deadline and is retried instead of blocking the job.
    Irsa.TIMEOUT = 25
    last_error = None
    for attempt in range(4):
        started = time.time()
        try:
            rows = _SEARCH_POOL.submit(Irsa.query_sia, pos=(SkyCoord(ra, dec, unit="deg"), 1 * u.arcsec),
                                       collection=list(COLLECTIONS)).result(timeout=SEARCH_TIMEOUT_S)
            log(f"search {ra:.4f} {dec:+.4f}: {len(rows)} images in {time.time() - started:.1f}s")
            break
        except Exception as error:  # IRSA under load resets connections
            last_error = error
            log(f"search attempt {attempt + 1} failed after {time.time() - started:.1f}s: {type(error).__name__}")
            time.sleep(2 * (attempt + 1))
    else:
        raise PipelineError(f"IRSA search failed: {type(last_error).__name__}") from last_error
    seen, observations = set(), []
    for row in rows:
        band, url = str(row["energy_bandpassname"]), str(row["access_url"])
        if not band.startswith("SPHEREx-D") or url in seen:
            continue
        seen.add(url)
        observations.append({
            "obs_id": str(row["obs_id"]), "detector": band.replace("SPHEREx-", ""),
            "access_url": url, "t_min": float(row["t_min"]), "t_max": float(row["t_max"]),
            "collection": str(row["obs_collection"]),
            "em_min_um": float(row["em_min"]) * 1e6, "em_max_um": float(row["em_max"]) * 1e6,
            "cloud_url": parse_cloud_url(str(row["cloud_access"])) if "cloud_access" in rows.colnames else None,
        })
    observations.sort(key=lambda r: r["t_min"])
    result = {"ra_deg": ra, "dec_deg": dec, "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "collections": list(COLLECTIONS), "observations": observations}
    path.write_text(json.dumps(result), encoding="utf-8")
    return result


def detector_counts(observations):
    return {d: sum(1 for o in observations if o["detector"] == d) for d in DETECTORS}


def cutout_url(observation, ra, dec, fov):
    return observation["access_url"] + "?" + urlencode({"center": f"{ra},{dec}d", "size": f"{fov:g}"})


def download_all(rows, ra, dec, fov, progress):
    CUTOUTS.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=WORKERS, pool_maxsize=WORKERS))
    jobs = []
    for row in rows:
        url = cutout_url(row, ra, dec, fov)
        jobs.append((row, url, CUTOUTS / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".fits")))
    done, failed = [], []
    stop = threading.Event()

    sources = {"cache": 0, "cutout": 0, "cloud": 0}

    def fetch(job):
        row, url, path = job
        if path.exists():
            sources["cache"] += 1
            return job
        tmp = path.with_suffix(f".{threading.get_ident()}.part")
        if SOURCE == "cloud" and row.get("cloud_url"):
            fetch_section(row["cloud_url"], ra, dec, fov, tmp, stop=stop)
            sources["cloud"] += 1
            tmp.replace(path)
            return job
        try:
            fetch_prefix(url, tmp, session=session, stop=stop, attempts=2)
            sources["cutout"] += 1
        except TimeoutError:
            raise
        except Exception:
            # The cutout service answers 503 under load; the public cloud copy does not.
            if not row.get("cloud_url"):
                raise
            fetch_section(row["cloud_url"], ra, dec, fov, tmp, stop=stop)
            sources["cloud"] += 1
        tmp.replace(path)
        return job

    pool = ThreadPoolExecutor(WORKERS)
    futures = {pool.submit(fetch, job): job for job in jobs}
    count = 0
    try:
        for future in as_completed(futures, timeout=DOWNLOAD_BUDGET_S):
            count += 1
            row, url, _ = futures[future]
            try:
                done.append(future.result())
            except Exception as error:
                failed.append({"obs_id": row["obs_id"], "url": url, "error": f"{type(error).__name__}: {error}"[:200]})
            progress("downloading", count, len(jobs))
    except FuturesTimeout:
        stop.set()  # running requests give up at their next retry
        for future, (row, url, _) in futures.items():
            if not future.done() or future.exception() is not None:
                if not any(f["url"] == url for f in failed):
                    failed.append({"obs_id": row["obs_id"], "url": url, "error": "not fetched within the time budget"})
            elif future.result() not in done:
                done.append(future.result())
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    log(f"downloads: {sources} failed {len(failed)}")
    return done, failed, sources


def select_rows(rows):
    """At most MAX_PER_VISIT frames per visit, spread evenly in time."""
    chosen = []
    for members in group_epochs([r["t_min"] for r in rows]):
        if len(members) > MAX_PER_VISIT:
            members = [members[i] for i in np.linspace(0, len(members) - 1, MAX_PER_VISIT).round().astype(int)]
        chosen.extend(rows[i] for i in members)
    return sorted(chosen, key=lambda r: r["t_min"])


# --------------------------------------------------------------------------- processing

def wavetable(detector):
    path = WAVETABLES / f"{detector}.fits"
    if not path.exists():
        return None
    with fits.open(path) as hdus:
        return fits.BinTableHDU(data=hdus[1].data.copy(), header=hdus[1].header.copy())


def flagged(flags_hdu, names):
    bits = 0
    for key in flags_hdu.header:
        if key.startswith("MSKN") and flags_hdu.header[key] in names:
            bits |= 1 << int(key[4:])
    return (flags_hdu.data.astype(np.int64) & bits) != 0


QUALITY_FLAGS = {
    "TRANSIENT", "OVERFLOW", "SUR_ERROR", "NONFUNC", "DICHROIC",
    "MISSING_DATA", "HOT", "COLD", "FULLSAMPLE", "PHANMISS", "NONLINEAR",
    "PERSIST", "OUTLIER", "CROSSTALK", "GHOST", "GHOST_FPA", "GHOST_EXT",
    "STREAK", "BLOOM", "SNOWBALL", "HALO",
}


def process_frame(path, grid, size, center, table, background="model", clean=False):
    with fits.open(path, memmap=False) as hdus:
        image = hdus["IMAGE"].data.astype(float)
        zodi = hdus["ZODI"].data.astype(float)
        if zodi.shape != image.shape:
            raise ValueError("ZODI shape differs from IMAGE")
        variance = hdus["VARIANCE"].data.astype(float)
        spatial = WCS(hdus["IMAGE"].header, fobj=hdus)
        bad, used = unusable_mask(hdus["FLAGS"], clean=clean)
        sky = image - zodi if background == "model" else image
        aligned = align_bilinear(sky, spatial, grid, size, ~bad)
        aligned_bad = align_bilinear(bad.astype(float), spatial, grid, size) > 0.25
        if background != "none":
            aligned = subtract_background(aligned)
        aligned_var = align_bilinear(variance, spatial, grid, size, ~bad)
        valid_variance = np.isfinite(aligned_var) & (aligned_var > 0)
        aligned = np.where(valid_variance, aligned, np.nan)
        saturated = align_bilinear(flagged(hdus["FLAGS"], {"OVERFLOW", "SUR_ERROR"}).astype(float),
                                   spatial, grid, size) > 0.25
        wave = bandwidth = None
        if table is not None:
            with_table = fits.HDUList([fits.PrimaryHDU(), hdus["IMAGE"].copy(), table])
            spectral = WCS(hdus["IMAGE"].header, fobj=with_table, key="W")
            spectral.sip = None
            x, y = spatial.world_to_pixel(center)
            w, b = spectral.pixel_to_world(x, y)
            wave, bandwidth = float(w.to_value("um")), float(b.to_value("um"))
    return aligned, aligned_var, saturated, aligned_bad, wave, bandwidth, float(np.mean(bad)), float(np.mean(saturated)), used


def predicted(target, when, grid):
    """Catalog position at time `when`, as grid pixel; None if no proper motion is known."""
    if not target or target.get("pmra") is None or target.get("pmdec") is None:
        return None
    position = propagate(target["ra2000"], target["dec2000"], target["pmra"], target["pmdec"],
                         float(target.get("motion_epoch", 2000.0)), float(when.jyear))
    x, y = grid.world_to_pixel(SkyCoord(position["ra_deg"], position["dec_deg"], unit="deg"))
    return {"ra_deg": position["ra_deg"], "dec_deg": position["dec_deg"],
            "grid_pixel": {"x": float(x), "y": float(y)},
            "source": target.get("motion_source") or target.get("source") or "catalog"}


# --------------------------------------------------------------------------- rendering

def stretch(array, low, high):
    scaled = np.arcsinh(10 * np.clip((array - low) / (high - low), 0, 1)) / np.arcsinh(10)
    return np.uint8(np.nan_to_num(scaled) * 255)


def display_bbox(valid_maps):
    """Smallest common rectangle containing valid sky pixels.

    Only rendered padding is removed; the full native grid remains in NPZs.
    """
    valid = np.logical_or.reduce(valid_maps)
    ys, xs = np.where(valid)
    if not len(xs):
        return (0, 0, valid.shape[1], valid.shape[0])
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def crop_array(array, bbox):
    x0, y0, x1, y1 = bbox
    return array[y0:y1, x0:x1]


def render(pixels, invalid, saturated, scale, saturated_value=255, smooth=True, bbox=None):
    if bbox is not None:
        pixels = crop_array(pixels, bbox)
        invalid = crop_array(invalid, bbox)
        saturated = crop_array(saturated, bbox)
    rgb = np.stack([pixels] * 3, axis=-1)
    rgb[invalid] = INVALID_RGB
    rgb[invalid & saturated] = saturated_value  # too bright, not missing
    # Masked detector corners are padding for display, not science pixels.
    # Transparency preserves the footprint without painting an artificial
    # rectangle over it; the original aligned arrays remain untouched.
    alpha = np.where(invalid & ~saturated, 0, 255).astype(np.uint8)
    # Grid row 0 is south: flip so north is up (east is already left).
    image = Image.fromarray(np.dstack([np.flipud(rgb), np.flipud(alpha)]), "RGBA")
    # Bilinear interpolation is display-only. FITS-derived arrays and the
    # aligned science grid are retained at native resolution in NPZ files.
    method = Image.Resampling.BILINEAR if smooth else Image.Resampling.NEAREST
    return image.resize((image.width * scale, image.height * scale), method)


def render_difference(first, second, saturated, scale, path, smooth=True, bbox=None):
    """Second minus first on a symmetric scale: white = brighter later, black = fainter."""
    delta = second - first
    both = np.isfinite(delta)
    limit = float(np.nanpercentile(np.abs(delta[both]), 99.5)) if both.any() else 1.0
    limit = limit or 1.0
    pixels = np.uint8(np.clip(127.5 + 127.5 * np.nan_to_num(delta) / limit, 0, 255))
    render(pixels, ~both, saturated, scale, saturated_value=128, smooth=smooth, bbox=bbox).save(path)
    return limit


def pair_difference(key, detector, a, b):
    """PNG of visit b minus visit a for a finished sequence (cached). None if unavailable."""
    folder = SEQUENCES / key / detector
    path = folder / "pairs" / f"{a}-{b}.png"
    if path.exists():
        return path
    files = [folder / "visits" / f"{i}.npz" for i in (a, b)]
    if a == b or not all(f.exists() for f in files):
        return None
    with np.load(files[0]) as first, np.load(files[1]) as second:
        size = first["stack"].shape[0]
        path.parent.mkdir(exist_ok=True)
        bbox = display_bbox([np.isfinite(first["stack"]), np.isfinite(second["stack"])])
        render_difference(first["stack"], second["stack"], first["saturated"] | second["saturated"],
                          max(2, round(470 / size)), path, bbox=bbox)
    return path


def display_fraction(pixel, size, bbox=None):
    x0, y0, x1, y1 = bbox or (0, 0, size, size)
    return {"x": (pixel["x"] - x0 + 0.5) / (x1 - x0),
            "y": (y1 - pixel["y"] - 0.5) / (y1 - y0)}


# --------------------------------------------------------------------------- main entry

def run(ra, dec, detector="D6", fov=0.1, target=None, progress=lambda stage, done, total: None,
        background="model", clean=False, smooth=True):
    """Build (or rebuild) the sequence for one position and detector. Returns the manifest."""
    if detector not in DETECTORS:
        raise PipelineError("Unknown detector")
    if fov not in FOVS:
        raise PipelineError("Unsupported field of view")
    if background not in BACKGROUNDS:
        raise PipelineError("Unknown background mode")
    started = time.time()
    progress("searching", 0, 1)
    archive = query_observations(ra, dec)
    counts = detector_counts(archive["observations"])
    rows = [o for o in archive["observations"] if o["detector"] == detector]
    if not rows:
        raise PipelineError(f"SPHEREx has no {detector} images of this position yet")
    available = len(rows)
    rows = select_rows(rows)
    downloaded, failed, sources = download_all(rows, ra, dec, fov, progress)

    grid, size = make_grid(ra, dec, fov_deg=fov)
    center = SkyCoord(ra, dec, unit="deg")
    table = wavetable(detector)
    frames = []
    for count, (row, url, path) in enumerate(sorted(downloaded, key=lambda j: j[0]["t_min"]), 1):
        progress("processing", count, len(downloaded))
        try:
            data, variance, saturated, mask, wave, bandwidth, source_mask_fraction, saturated_fraction, mask_flags = process_frame(
                path, grid, size, center, table, background, clean)
        except Exception as error:
            failed.append({"obs_id": row["obs_id"], "url": url, "error": f"{type(error).__name__}: {error}"[:200]})
            continue
        if np.isfinite(data).mean() < 0.2:
            failed.append({"obs_id": row["obs_id"], "url": url, "error": "covers less than 20% of the field"})
            continue
        frames.append({"row": row, "url": url, "data": data, "variance": variance, "mask": mask,
                       "saturated": saturated, "wave": wave, "bandwidth": bandwidth,
                       "source_mask_fraction": source_mask_fraction,
                       "saturated_fraction": saturated_fraction, "mask_flags": mask_flags})
    if not frames:
        raise PipelineError("No usable frames could be downloaded; IRSA may be busy, try again shortly")

    # Visits: stack frames taken within a few weeks of each other.
    groups = group_epochs([f["row"]["t_min"] for f in frames])
    for visit, members in enumerate(groups):
        for i in members:
            frames[i]["visit"] = visit
    min_frames = MIN_VISIT_FRAMES if sum(len(g) >= MIN_VISIT_FRAMES for g in groups) >= 2 else 2
    visits, skipped = [], []
    for members in groups:
        group = [frames[i] for i in members]
        times = [f["row"]["t_min"] for f in group]
        if len(group) < min_frames:
            skipped.append({"time_start_utc": Time(min(times), format="mjd").isot, "n_frames": len(group)})
            continue
        # Saturated cores and invalid-variance pixels are never allowed into a
        # visit stack. The original arrays remain available in frame NPZ files.
        stack_data = np.stack([np.where(f["saturated"], np.nan, f["data"]) for f in group])
        stacked, _ = combine(stack_data, np.stack([f["variance"] for f in group]))
        mean_time = Time(float(np.mean(times)), format="mjd")
        visits.append({"stack": stacked, "group": group, "times": times, "mean_time": mean_time,
                       "saturated": np.logical_or.reduce([f["saturated"] for f in group]),
                       "predicted": predicted(target, mean_time, grid)})

    progress("rendering", 0, 1)
    out = output_dir(ra, dec, detector, fov, background, clean, smooth)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    (out / "masks").mkdir(parents=True, exist_ok=True)
    (out / "visits").mkdir(parents=True, exist_ok=True)
    scale = max(2, round(470 / size))
    base = f"/api/sequence/{sequence_key(ra, dec, fov, background, clean, smooth)}/{detector}"
    # One common crop keeps animation stable while removing only empty padding.
    display_crop = display_bbox([np.isfinite(frame["data"]) for frame in frames])

    # Single frames share one display scale; visit stacks (less noisy) get their own.
    frame_values = np.concatenate([f["data"][np.isfinite(f["data"]) & ~f["saturated"]] for f in frames])
    f_low, f_high = (float(v) for v in np.percentile(frame_values, [1, 99.7]))
    if background == "none":
        # Raw sky: anchor black at zero flux so the zodiacal glow stays visible as a
        # grey background instead of being absorbed by the percentile stretch.
        f_low -= float(np.median(frame_values))
    frame_items = []
    for index, frame in enumerate(frames):
        render(stretch(frame["data"], f_low, f_high), ~np.isfinite(frame["data"]), frame["saturated"],
               scale, smooth=smooth, bbox=display_crop).save(out / "frames" / f"{index}.png")
        mask_image = np.zeros((*frame["mask"].shape, 3), dtype=np.uint8)
        mask_image[frame["mask"]] = (255, 166, 64)
        mask_image = crop_array(mask_image, display_crop)
        Image.fromarray(np.flipud(mask_image)).resize((mask_image.shape[1] * scale, mask_image.shape[0] * scale), Image.Resampling.NEAREST).save(
            out / "masks" / f"{index}.png")
        np.savez_compressed(out / "frames" / f"{index}.npz", data=frame["data"].astype(np.float32),
                            variance=frame["variance"].astype(np.float32), saturated=frame["saturated"])
        when = Time(frame["row"]["t_min"], format="mjd")
        guess = predicted(target, when, grid)
        frame_items.append({
            "index": index, "time_utc": when.isot, "visit": frame["visit"],
            "release": frame["row"]["collection"].replace("spherex_", "").upper(),
            "obs_id": frame["row"]["obs_id"],
            "wavelength_um": frame["wave"], "bandwidth_um": frame["bandwidth"],
            "usable_grid_fraction": float(np.isfinite(frame["data"]).mean()),
            "masked_fraction": frame["source_mask_fraction"],
            "mask_flags": frame["mask_flags"],
            "saturated_fraction": frame["saturated_fraction"],
            "image_url": f"{base}/frames/{index}.png", "mask_url": f"{base}/masks/{index}.png", "cutout_url": frame["url"],
            "predicted_position": guess and {**guess, "display_fraction": display_fraction(guess["grid_pixel"], size, display_crop)},
            "photometry": (aperture_photometry(frame["data"], frame["variance"],
                            guess["grid_pixel"]["x"], guess["grid_pixel"]["y"])
                           if guess else None),
            "saturated_at_target": (bool(frame["saturated"][int(round(guess["grid_pixel"]["y"])) , int(round(guess["grid_pixel"]["x"]))])
                                     if guess and 0 <= int(round(guess["grid_pixel"]["y"])) < size and 0 <= int(round(guess["grid_pixel"]["x"])) < size else False),
        })

    visit_items, annotated = [], []
    if visits:
        common = np.logical_and.reduce([np.isfinite(v["stack"]) for v in visits])
        values = np.concatenate([v["stack"][common] for v in visits]) if common.any() else frame_values
        v_low, v_high = (float(x) for x in np.percentile(values, [2, 99.5]))
        if background == "none":
            v_low -= float(np.median(values))
        for index, visit in enumerate(visits):
            image = render(stretch(visit["stack"], v_low, v_high), ~np.isfinite(visit["stack"]),
                           visit["saturated"], scale, smooth=smooth, bbox=display_crop)
            image.save(out / "visits" / f"{index}.png")
            # Kept so any two visits can be differenced on request (see pair_difference).
            np.savez_compressed(out / "visits" / f"{index}.npz", stack=visit["stack"].astype(np.float32),
                                saturated=visit["saturated"])
            waves = [f["wave"] for f in visit["group"] if f["wave"] is not None]
            guess = visit["predicted"]
            measured = measure_source(visit["stack"], guess["grid_pixel"]["x"], guess["grid_pixel"]["y"]) if guess else None
            canvas = Image.new("RGB", (image.width, image.height + 40), "#101827")
            canvas.paste(image, (0, 40))
            ImageDraw.Draw(canvas).text(
                (8, 12), f"{visit['mean_time'].isot[:10]} | {len(visit['group'])} frames | SPHEREx {detector}", fill="white")
            annotated.append(canvas)
            visit_items.append({
                "index": index, "time_utc": visit["mean_time"].isot,
                "time_start_utc": Time(min(visit["times"]), format="mjd").isot,
                "time_end_utc": Time(max(visit["times"]), format="mjd").isot,
                "n_frames": len(visit["group"]),
                "wavelength_min_um": min(waves) if waves else None,
                "wavelength_max_um": max(waves) if waves else None,
                "usable_grid_fraction": float(np.isfinite(visit["stack"]).mean()),
                "saturated_fraction": float(np.mean([f["saturated_fraction"] for f in visit["group"]])) if visit["group"] else 0.0,
                "image_url": f"{base}/visits/{index}.png",
                "cutout_url": visit["group"][0]["url"],
                "predicted_position": guess and {**guess, "display_fraction": display_fraction(guess["grid_pixel"], size, display_crop)},
                "measured_position": measured,
            })
        annotated[0].save(out / "blink.gif", save_all=True, append_images=annotated[1:], duration=700, loop=0)

    difference = None
    if len(visits) >= 2:
        limit = render_difference(visits[0]["stack"], visits[-1]["stack"],
                                  visits[0]["saturated"] | visits[-1]["saturated"], scale, out / "difference.png",
                                  smooth=smooth, bbox=display_crop)
        difference = {"image_url": f"{base}/difference.png", "symmetric_limit": limit,
                      "from_utc": visit_items[0]["time_utc"], "to_utc": visit_items[-1]["time_utc"],
                      "description": "last visit minus first visit: white = brighter now, black = fainter now"}

    manifest = {
        "kind": "sequence",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query": {"ra_deg": ra, "dec_deg": dec, "detector": detector, "fov_deg": fov,
                  "key": sequence_key(ra, dec, fov, background, clean, smooth), "background": background,
                  "clean_mask": clean, "smooth_display": smooth},
        "target": target,
        "display": {"crop": {"x0": display_crop[0], "y0": display_crop[1],
                               "x1": display_crop[2], "y1": display_crop[3]},
                     "native_size": size, "preserves_native_data": True},
        "archive": {"collections": list(COLLECTIONS), "retrieved_at": archive["retrieved_at"],
                    "observations_by_detector": counts},
        "frames": frame_items,
        "visits": visit_items,
        "skipped_visits": skipped,
        "difference": difference,
        "grid": {"size_px": size, "pixel_arcsec": 6.2, "orientation": "north up, east left",
                 "header": dict(grid.to_header())},
        "processing": {
            "steps": ["image part of each IRSA cutout only (no PSF table); if the cutout service is busy, "
                      "the same pixels are read from NASA's public cloud copy",
                      "IMAGE minus supplied ZODI model", "unusable FLAGS masked, saturated cores marked",
                      "bilinear resampling onto a fixed sky grid", "sky level (sigma-clipped median) removed",
                      "visit stack: inverse-variance weighted mean with per-pixel MAD sigma clipping"],
            "frame_display": {"low": f_low, "high": f_high},
            "frames_available": available, "frames_requested": len(rows),
            "frames_used": len(frames), "frames_failed": len(failed), "download_sources": sources,
            "seconds": round(time.time() - started, 1),
            "wavelengths": "per-detector lookup table" if table is not None else "unavailable",
            "quality_mask": "full artifact mask" if clean else "conservative mask",
            "display_resampling": "bilinear" if smooth else "nearest",
        },
        "failures": failed,
        "warnings": [
            "Frames within a visit cover different wavelengths of the detector band; brightness changes can be spectral.",
            "Saturated star cores are excluded from the data and drawn white.",
            "Images are for visual inspection: no PSF matching or calibrated photometry.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    log(f"{sequence_key(ra, dec, fov, background, clean, smooth)} {detector}: {len(frames)} frames, {len(visits)} visits, "
        f"{len(failed)} failed, {time.time() - started:.1f}s")
    progress("done", 1, 1)
    return manifest


def load(ra, dec, detector, fov, background="model", clean=False, smooth=True):
    path = output_dir(ra, dec, detector, fov, background, clean, smooth) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
