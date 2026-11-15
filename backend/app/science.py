"""Small, auditable science products built from prepared sequence manifests.

These helpers deliberately consume only values produced by the pipeline.  They
do not fabricate detections when a detector or visit is missing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math

import numpy as np
from PIL import Image

DETECTOR_BANDS = {
    "D1": (0.75, 1.10), "D2": (1.10, 1.62), "D3": (1.62, 2.42),
    "D4": (2.42, 3.82), "D5": (3.82, 4.40), "D6": (4.40, 5.00),
}
COLOUR_PAIRS = {"blue": ("D1", "D2"), "green": ("D3", "D4"), "red": ("D5", "D6")}


def overlap(a_min, a_max, b_min, b_max):
    """Return the common wavelength interval, or None."""
    if None in (a_min, a_max, b_min, b_max):
        return None
    low, high = max(float(a_min), float(b_min)), min(float(a_max), float(b_max))
    return {"min_um": low, "max_um": high} if high > low else None


def visit_quality(visit, frame_count=None):
    """Classify coverage without implying scientific validity."""
    coverage = float(visit.get("usable_grid_fraction") or 0)
    count = int(frame_count if frame_count is not None else visit.get("n_frames") or 0)
    saturation = float(visit.get("saturated_fraction") or 0)
    if coverage >= .85 and count >= 8 and saturation < .2:
        level = "good"
    elif coverage >= .55 and count >= 3:
        level = "partial"
    else:
        level = "poor"
    return {"level": level, "usable_fraction": round(coverage, 3), "frames": count, "saturated_fraction": round(saturation, 3),
            "note": "coverage and frame count only; not a calibrated science quality score"}


def matched_range(visit_a, visit_b):
    return overlap(visit_a.get("wavelength_min_um"), visit_a.get("wavelength_max_um"),
                   visit_b.get("wavelength_min_um"), visit_b.get("wavelength_max_um"))


def matched_difference(sequence_root: Path, manifest: dict, a: int, b: int, output: Path):
    """Diagnostic B-A with compatible local passbands and inverse variance weights.

    The reference is the first usable A exposure at each grid pixel. Only
    measurements within one quarter of the narrower local FWHM enter a stack.
    Resampling correlations, PSF and background uncertainty remain limitations.
    """
    from astropy.io import fits
    visits = manifest.get("visits", [])
    if a < 0 or b < 0 or a == b or max(a, b) >= len(visits):
        return None
    groups = {a: [], b: []}
    for item in manifest.get("frames", []):
        visit = item.get("visit")
        if visit not in groups:
            continue
        path = sequence_root / "frames" / f"{item['index']}.npz"
        if not path.exists():
            continue
        with np.load(path) as source:
            if not {"wavelength_um", "bandwidth_um", "variance", "saturated"}.issubset(source.files):
                continue  # old center-wavelength products require regeneration
            groups[visit].append({name: np.array(source[name]) for name in
                                  ("data", "variance", "saturated", "wavelength_um", "bandwidth_um")})
    if not groups[a] or not groups[b]:
        return None
    shape = groups[a][0]["data"].shape
    reference, width = np.full(shape, np.nan), np.full(shape, np.nan)
    def valid(frame):
        return (np.isfinite(frame["data"]) & np.isfinite(frame["variance"]) & (frame["variance"] > 0)
                & ~frame["saturated"] & np.isfinite(frame["wavelength_um"])
                & np.isfinite(frame["bandwidth_um"]) & (frame["bandwidth_um"] > 0))
    for frame in groups[a]:
        select = ~np.isfinite(reference) & valid(frame)
        reference[select] = frame["wavelength_um"][select]
        width[select] = frame["bandwidth_um"][select]
    def stack(frames):
        weighted, total, count = np.zeros(shape), np.zeros(shape), np.zeros(shape, dtype=np.int32)
        for frame in frames:
            tolerance = .25 * np.minimum(width, frame["bandwidth_um"])
            usable = valid(frame) & (np.abs(frame["wavelength_um"] - reference) <= tolerance)
            weight = np.divide(1., frame["variance"], out=np.zeros(shape), where=usable)
            weighted += np.where(usable, frame["data"], 0) * weight
            total += weight
            count += usable
        mean = np.divide(weighted, total, out=np.full(shape, np.nan), where=total > 0)
        variance = np.divide(1., total, out=np.full(shape, np.nan), where=total > 0)
        return mean, variance, count
    first, var_a, count_a = stack(groups[a])
    second, var_b, count_b = stack(groups[b])
    delta = second - first
    finite = np.isfinite(delta)
    if not finite.any():
        return None
    limit = float(np.percentile(np.abs(delta[finite]), 99.5)) or 1.
    pixels = np.uint8(np.clip(127.5 + 127.5 * np.nan_to_num(delta) / limit, 0, 255))
    rgb = np.repeat(pixels[..., None], 3, axis=-1)
    rgb[~finite] = (45, 35, 55)
    output.parent.mkdir(parents=True, exist_ok=True)
    import uuid
    temporary = output.with_name(output.stem + '.' + uuid.uuid4().hex + '.png')
    Image.fromarray(np.flipud(rgb)).save(temporary)
    temporary.replace(output)
    header = fits.Header(manifest.get("grid", {}).get("header", {}))
    header['BUNIT'] = manifest.get("processing", {}).get("unit", 'MJy/sr')
    header['HISTORY'] = 'Diagnostic B-A; local passband tolerance 0.25 FWHM. No PSF matching.'
    header['VISIT_A'], header['VISIT_B'] = a, b
    fits.HDUList([fits.PrimaryHDU(delta.astype(np.float32), header=header),
                  fits.ImageHDU((var_a + var_b).astype(np.float32), name='VARIANCE'),
                  fits.ImageHDU(count_a, name='COUNT_A'), fits.ImageHDU(count_b, name='COUNT_B'),
                  fits.ImageHDU((~finite).astype(np.uint8), name='MASK'),
                  fits.ImageHDU(reference.astype(np.float32), name='WAVELENGTH')]).writeto(output.with_suffix('.fits'), overwrite=True)
    return {"frames_a": len(groups[a]), "frames_b": len(groups[b]),
            "usable_grid_fraction": float(finite.mean()), "image_url": str(output)}


def spectrum(manifests):
    """Return measured frame fluxes, sorted by wavelength, for a target."""
    points = []
    for manifest in manifests:
        for frame in manifest.get("frames", []):
            photometry = frame.get("photometry") or {}
            wavelength = frame.get("wavelength_um")
            flux = photometry.get("flux")
            if wavelength is not None and flux is not None and math.isfinite(float(flux)) and not frame.get("saturated_at_target", False):
                points.append({"wavelength_um": float(wavelength), "flux": float(flux),
                               "error": photometry.get("error"), "snr": photometry.get("snr"),
                               "detector": manifest.get("query", {}).get("detector"),
                               "visit": frame.get("visit"),
                               "time_utc": frame.get("time_utc"),
                               "saturated": bool(frame.get("saturated", False))})
    return sorted(points, key=lambda p: (p["time_utc"] or "", p["wavelength_um"]))


def _read_visit(path):
    """Read the aligned science stack, not its display PNG."""
    with np.load(path) as data:
        return np.array(data["stack"], dtype=np.float32)


def _fill_display_gaps(channel, footprint):
    """Fill interior display holes from the nearest valid pixel.

    This is used only for the false-colour PNG. The original masked arrays in
    the visit NPZ files are never changed, and the outer detector footprint
    remains transparent.
    """
    finite = np.isfinite(channel)
    if finite.all() or not finite.any():
        return np.nan_to_num(channel)
    filled = np.nan_to_num(channel).astype(np.float32, copy=True)
    known = finite.copy()
    ys, xs = np.where(footprint)
    fill_region = np.zeros_like(footprint)
    if len(xs):
        fill_region[ys.min():ys.max() + 1, xs.min():xs.max() + 1] = True
    # Expand valid pixels through the small display grid. This is deliberately
    # simple and dependency-free; it affects only display holes.
    for _ in range(max(channel.shape)):
        if np.all(known | ~fill_region):
            break
        total = np.zeros_like(filled, dtype=np.float32)
        count = np.zeros_like(filled, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted_known = np.roll(known, (dy, dx), axis=(0, 1))
            shifted_values = np.roll(filled, (dy, dx), axis=(0, 1))
            total += np.where(shifted_known, shifted_values, 0)
            count += shifted_known
        holes = fill_region & ~known & (count > 0)
        filled[holes] = total[holes] / count[holes]
        known[holes] = True
    return np.nan_to_num(filled)


def colour_composite(sequence_root: Path, detector_manifests: dict, visit_index: int, output: Path):
    """Build D1+D2 / D3+D4 / D5+D6 from aligned science visit stacks."""
    reference = detector_manifests.get("D6") or next(iter(detector_manifests.values()), None)
    reference_visits = (reference or {}).get("visits", [])
    if visit_index >= len(reference_visits):
        return None
    reference_time = reference_visits[visit_index].get("time_utc")
    channels = []
    for channel, pair in COLOUR_PAIRS.items():
        images = []
        for detector in pair:
            manifest = detector_manifests.get(detector)
            visits = (manifest or {}).get("visits", [])
            if not visits:
                return None
            def distance(item):
                try:
                    return abs((datetime.fromisoformat(item.get("time_utc", "").replace("Z", "+00:00")) -
                                datetime.fromisoformat(reference_time.replace("Z", "+00:00"))).total_seconds())
                except (ValueError, TypeError):
                    return 0
            chosen = min(visits, key=distance) if reference_time else visits[0]
            chosen_index = chosen.get("index", 0)
            root = sequence_root / detector
            if manifest.get("generation"):
                root = root / "generations" / manifest["generation"]
            path = root / "visits" / f"{chosen_index}.npz"
            if not path.exists():
                return None
            images.append(_read_visit(path))
        channels.append(np.nanmean(images, axis=0))
    channel_cube = np.stack(channels, axis=-1)
    footprint = np.any(np.isfinite(channel_cube), axis=-1)
    ys, xs = np.where(footprint)
    display_region = np.zeros_like(footprint)
    if len(xs):
        display_region[ys.min():ys.max() + 1, xs.min():xs.max() + 1] = True
    display_channels = {}
    scales = {}
    for name, channel in zip(("blue", "green", "red"), channels):
        finite = channel[np.isfinite(channel)]
        if not len(finite):
            return None
        low, high = np.percentile(finite, [2, 99.5])
        scales[name] = {"low": float(low), "high": float(high)}
        display = _fill_display_gaps(channel, footprint)
        display_channels[name] = np.clip((display - low) / max(high - low, 1e-6), 0, 1)
    # PIL's RGB order is red, green, blue; the broadband mapping above is
    # intentionally described in blue, green, red order for users.
    rgb = np.uint8(np.stack([display_channels["red"], display_channels["green"], display_channels["blue"]], axis=-1) * 255)
    common_valid = np.all(np.isfinite(channel_cube), axis=-1)
    bright = np.zeros_like(footprint)
    for channel in channels:
        finite = channel[np.isfinite(channel)]
        if len(finite):
            bright |= np.isfinite(channel) & (channel >= np.percentile(finite, 99.5))
    # Grow bright valid pixels over a small masked core for display. This
    # neutralizes saturated star holes without inventing coloured structure.
    for _ in range(3):
        grown = bright.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            grown |= np.roll(bright, (dy, dx), axis=(0, 1))
        bright = grown
    display_saturated = bright & ~common_valid & footprint
    rgb[display_saturated] = 255
    alpha = np.where(display_region | display_saturated, 255, 0).astype(np.uint8)
    rgba = np.dstack([np.flipud(rgb), np.flipud(alpha)])
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(rgba, "RGBA")
    # The aligned science grid is intentionally small (6.2 arcsec/pixel). Make
    # the display product the same useful size as the normal sequence viewer;
    # this changes only the PNG, never the underlying NPZ arrays.
    scale = max(2, round(470 / image.width))
    image.resize((image.width * scale, image.height * scale), Image.Resampling.BILINEAR).save(output)
    return {"visit": visit_index, "image_url": str(output), "channels": COLOUR_PAIRS,
            "display_scale": scales, "matched_by": "nearest visit timestamp"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()
