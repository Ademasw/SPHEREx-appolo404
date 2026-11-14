"""Download every cutout of one detector for a target and build per-visit stacks.

Run from the repository root after scripts.audit_targets:

    python -m scripts.prepare_stack --target wise-0855 --detector D6

Outputs go to data/stacks/<target>/<detector>/: one PNG per visit (epoch),
a last-minus-first difference PNG, an annotated blink GIF and manifest.json.
"""
import argparse
import hashlib
import json
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS, FITSFixedWarning
from PIL import Image, ImageDraw

from app.archive import ROOT, save_report, search
from app.astrometry import propagate
from app.preview import make_grid, unusable_mask
from app.stack import align_bilinear, combine, group_epochs, measure_source, subtract_background
from scripts.prepare_preview import download

warnings.simplefilter("ignore", FITSFixedWarning)
SCALE = 8  # display upscaling, nearest neighbor
INVALID_RGB = (45, 35, 55)


def load_target(target_id):
    audit = json.loads((ROOT / "data/catalog/audit.json").read_text(encoding="utf-8"))
    for entry in audit["targets"]:
        if entry["id"] == target_id:
            if "error" in entry:
                raise ValueError(f"Catalog audit failed for {target_id}: {entry['error']}")
            return entry
    raise ValueError(f"Unknown target {target_id}; run scripts.audit_targets first")


def load_observations(ra, dec, release):
    path = ROOT / "data/metadata" / f"{ra:.7f}_{dec:.7f}_{release}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    report = search(ra, dec, release)
    save_report(report)
    return report


def fetch_all(rows, ra, dec, fov, workers):
    raw = ROOT / "data/cutouts"
    raw.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for row in rows:
        url = row["access_url"] + "?" + urlencode({"center": f"{ra},{dec}", "size": str(fov)})
        jobs[url] = (row, raw / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".fits"))
    done, failed = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download, url, path): url for url, (row, path) in jobs.items()}
        for count, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            try:
                future.result()
                done.append((jobs[url][0], jobs[url][1], url))
            except Exception as error:  # keep going: IRSA returns transient 503s
                failed.append({"url": url, "error": f"{type(error).__name__}: {error}"})
            print(f"  cutouts {count}/{len(jobs)} (failed {len(failed)})", end="\r", flush=True)
    print()
    return done, failed


def process_frame(path, grid, size, center):
    with fits.open(path, memmap=False) as hdus:
        image = hdus["IMAGE"].data.astype(float)
        zodi = hdus["ZODI"].data.astype(float)
        if zodi.shape != image.shape:
            raise ValueError("ZODI shape differs from IMAGE")
        variance = hdus["VARIANCE"].data.astype(float)
        spatial = WCS(hdus["IMAGE"].header, fobj=hdus)
        bad, _ = unusable_mask(hdus["FLAGS"])
        aligned = subtract_background(align_bilinear(image - zodi, spatial, grid, size, ~bad))
        aligned_var = align_bilinear(variance, spatial, grid, size, ~bad)
        spectral = WCS(hdus["IMAGE"].header, fobj=hdus, key="W")
        spectral.sip = None
        x, y = spatial.world_to_pixel(center)
        wave, _ = spectral.pixel_to_world(x, y)
    return aligned, aligned_var, float(wave.to_value("um"))


def stretch(array, low, high):
    scaled = np.arcsinh(10 * np.clip((array - low) / (high - low), 0, 1)) / np.arcsinh(10)
    return np.uint8(np.nan_to_num(scaled) * 255)


def to_image(pixels, invalid):
    rgb = np.stack([pixels] * 3, axis=-1)
    rgb[invalid] = INVALID_RGB
    # Row 0 of the grid is south; flip so north is up (east is already left).
    return Image.fromarray(np.flipud(rgb)).resize(
        (pixels.shape[1] * SCALE, pixels.shape[0] * SCALE), Image.Resampling.NEAREST)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, help="target id from data/catalog/audit.json")
    parser.add_argument("--detector", default="D6", choices=[f"D{i}" for i in range(1, 7)])
    parser.add_argument("--release", default="dr1", choices=["dr1", "qr3"])
    parser.add_argument("--fov", type=float, default=0.1, help="field of view, degrees")
    parser.add_argument("--gap-days", type=float, default=30.0, help="gap that separates visits")
    parser.add_argument("--min-frames", type=int, default=5, help="skip visits with fewer frames")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    target = load_target(args.target)
    ra, dec = target["search_position"]["ra_deg"], target["search_position"]["dec_deg"]
    center = SkyCoord(ra, dec, unit="deg")
    report = load_observations(ra, dec, args.release)
    band = f"SPHEREx-{args.detector}"
    rows = sorted((r for r in report["observations"] if r.get("energy_bandpassname") == band),
                  key=lambda r: r["t_min"])
    if not rows:
        raise SystemExit(f"No {band} observations for {args.target}")
    print(f"{target['name']}: {len(rows)} {band} observations; downloading cutouts...", flush=True)
    downloaded, failed = fetch_all(rows, ra, dec, args.fov, args.workers)

    grid, size = make_grid(ra, dec, fov_deg=args.fov)
    frames = []
    for row, path, url in sorted(downloaded, key=lambda item: item[0]["t_min"]):
        try:
            aligned, variance, wave = process_frame(path, grid, size, center)
        except Exception as error:
            failed.append({"url": url, "error": f"{type(error).__name__}: {error}"})
            continue
        if np.isfinite(aligned).mean() < 0.2:
            failed.append({"url": url, "error": "less than 20% of the grid covered"})
            continue
        frames.append({"row": row, "url": url, "data": aligned, "variance": variance, "wave": wave})
    if not frames:
        raise SystemExit("No usable frames")

    catalog = target["catalog"]
    epochs, skipped = [], []
    for members in group_epochs([f["row"]["t_min"] for f in frames], args.gap_days):
        group = [frames[i] for i in members]
        if len(group) < args.min_frames:
            skipped.append({"time_start_utc": Time(group[0]["row"]["t_min"], format="mjd").isot,
                            "n_frames": len(group),
                            "reason": f"fewer than {args.min_frames} usable frames; too noisy to compare"})
            continue
        stacked, used = combine(np.stack([f["data"] for f in group]),
                                np.stack([f["variance"] for f in group]))
        times = [f["row"]["t_min"] for f in group]
        waves = [f["wave"] for f in group]
        mean_time = Time(float(np.mean(times)), format="mjd")
        predicted = propagate(float(catalog["ra"]), float(catalog["dec"]), float(catalog["pmra"]),
                              float(catalog["pmdec"]), 2000.0, float(mean_time.jyear))
        px, py = grid.world_to_pixel(SkyCoord(predicted["ra_deg"], predicted["dec_deg"], unit="deg"))
        epochs.append({"stack": stacked, "used": used, "group": group, "times": times, "waves": waves,
                       "mean_time": mean_time, "predicted": predicted, "pixel": (float(px), float(py)),
                       "measured": measure_source(stacked, float(px), float(py))})
    if not epochs:
        raise SystemExit(f"No visit has at least {args.min_frames} usable frames")

    common = np.logical_and.reduce([np.isfinite(e["stack"]) for e in epochs])
    if common.sum() < 25:
        raise SystemExit("Visits do not overlap enough on the grid")
    values = np.concatenate([e["stack"][common] for e in epochs])
    low, high = (float(v) for v in np.percentile(values, [2, 99.5]))

    output = ROOT / "data/stacks" / args.target / args.detector
    output.mkdir(parents=True, exist_ok=True)
    base_url = f"/api/stack/{args.target}/{args.detector}"
    manifest_frames, annotated = [], []
    for index, epoch in enumerate(epochs):
        invalid = ~np.isfinite(epoch["stack"])
        image = to_image(stretch(epoch["stack"], low, high), invalid)
        image.save(output / f"{index}.png")
        px, py = epoch["pixel"]
        cx, cy = (px + 0.5) * SCALE, (size - py - 0.5) * SCALE  # display coordinates (flipped)
        canvas = Image.new("RGB", (image.width, image.height + 46), "#101827")
        canvas.paste(image, (0, 46))
        draw = ImageDraw.Draw(canvas)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):  # open crosshair, keeps the source visible
            draw.line([(cx + dx * 9, cy + 46 + dy * 9), (cx + dx * 20, cy + 46 + dy * 20)], fill="#ff9c66", width=2)
        draw.text((8, 6), f"{epoch['mean_time'].isot[:10]}  |  {len(epoch['group'])} frames stacked", fill="white")
        draw.text((8, 24), f"SPHEREx {args.release.upper()} {args.detector}  {min(epoch['waves']):.2f}-{max(epoch['waves']):.2f} um", fill="white")
        annotated.append(canvas)
        manifest_frames.append({
            "index": index,
            "time_utc": epoch["mean_time"].isot,
            "time_start_utc": Time(min(epoch["times"]), format="mjd").isot,
            "time_end_utc": Time(max(epoch["times"]), format="mjd").isot,
            "n_frames": len(epoch["group"]),
            "center_wavelength_um": float(np.mean(epoch["waves"])),
            "wavelength_min_um": float(min(epoch["waves"])),
            "wavelength_max_um": float(max(epoch["waves"])),
            "center_bandwidth_um": float(max(epoch["waves"]) - min(epoch["waves"])),
            "usable_grid_fraction": float(np.isfinite(epoch["stack"]).mean()),
            "image_url": f"{base_url}/frames/{index}",
            "cutout_url": epoch["group"][0]["url"],
            "cutout_urls": [f["url"] for f in epoch["group"]],
            "predicted_position": {
                **epoch["predicted"],
                "grid_pixel": {"x": px, "y": py},
                # fraction of the displayed image, origin top-left (north up, east left)
                "display_fraction": {"x": (px + 0.5) / size, "y": (size - py - 0.5) / size},
            },
            # centroid of the source nearest to the prediction; a check, not calibrated astrometry
            "measured_position": epoch["measured"],
        })
    annotated[0].save(output / "blink.gif", save_all=True, append_images=annotated[1:], duration=700, loop=0)

    difference = epochs[-1]["stack"] - epochs[0]["stack"]
    limit = float(np.nanpercentile(np.abs(difference[common]), 99.5)) or 1.0
    diff_pixels = np.uint8(np.clip(127.5 + 127.5 * difference / limit, 0, 255))
    to_image(diff_pixels, ~common).save(output / "difference.png")

    manifest = {
        "kind": "epoch_stack",
        "target": {"id": target["id"], "name": target["name"]},
        "query": {"ra_deg": ra, "dec_deg": dec, "release": args.release, "detector": args.detector,
                  "fov_deg": args.fov},
        "frames": manifest_frames,
        "difference": {"image_url": f"{base_url}/difference",
                       "description": "last visit minus first visit; black = fainter, white = brighter",
                       "symmetric_limit": limit},
        "grid": {"size_px": size, "pixel_arcsec": 6.2, "orientation": "north up, east left",
                 "header": dict(grid.to_header())},
        "processing": {
            "steps": ["IMAGE minus supplied ZODI model", "unusable FLAGS masked",
                      "bilinear resampling onto a fixed sky grid", "per-frame sigma-clipped median background removed",
                      "inverse-variance weighted mean per visit with per-pixel MAD sigma clipping"],
            "visit_gap_days": args.gap_days,
            "display_low": low, "display_high": high, "stretch": "shared asinh(10*x)", "units": "MJy/sr",
            "shared_valid_fraction": float(common.mean()),
            "frames_used": len(frames), "frames_failed": len(failed),
        },
        "skipped_visits": skipped,
        "failures": failed,
        "warnings": [
            "Each visit stack mixes the wavelengths of one detector band; brightness changes can be spectral.",
            "Predicted positions use catalog proper motion only (no parallax or orbital motion).",
            "Stacks are for visual inspection; no PSF matching or calibrated photometry.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Visits shown: {len(epochs)}, skipped {len(skipped)} | frames used {len(frames)}, failed {len(failed)}")
    for item in manifest_frames:
        predicted, measured = item["predicted_position"]["grid_pixel"], item["measured_position"]
        found = (f"measured ({measured['x']:.2f}, {measured['y']:.2f}) S/N {measured['peak_snr']:.1f}"
                 if measured else "no source measured")
        print(f"  {item['time_utc'][:10]}: {item['n_frames']} frames, "
              f"{item['wavelength_min_um']:.2f}-{item['wavelength_max_um']:.2f} um, "
              f"predicted ({predicted['x']:.2f}, {predicted['y']:.2f}), {found}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
