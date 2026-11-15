"""Download three bounded IRSA cutouts and create diagnostic preview products."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from PIL import Image, ImageDraw

from app.archive import ROOT
from app.preview import align_nearest, make_grid, unusable_mask
from app.display import grayscale_rgb


def download(url, path):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "irsa.ipac.caltech.edu":
        raise ValueError("Only official IRSA HTTPS URLs are allowed")
    if path.exists():
        with fits.open(path) as hdus:
            hdus["IMAGE"]
        return
    tmp = path.with_suffix(".part")
    for attempt in range(3):
        try:
            with requests.get(url, timeout=(15, 120), stream=True) as response:
                response.raise_for_status()
                count = 0
                with tmp.open("wb") as output:
                    for chunk in response.iter_content(65536):
                        count += len(chunk)
                        if count > 25 * 1024 * 1024:
                            raise ValueError("Cutout exceeded 25 MiB safety limit")
                        output.write(chunk)
            with fits.open(tmp) as hdus:
                hdus["IMAGE"]
            tmp.replace(path)
            return
        except (requests.RequestException, OSError):
            tmp.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / "data/metadata/133.7951292_-7.2451472_dr1.json")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    rows = [r for r in report["observations"] if r["energy_bandpassname"] == "SPHEREx-D6"]
    if len(rows) < 3:
        raise ValueError("Need at least three D6 observations")
    rows.sort(key=lambda row: row["t_min"])
    selected = [rows[0], rows[len(rows) // 2], rows[-1]]
    ra, dec = report["query"]["ra_deg"], report["query"]["dec_deg"]
    output = ROOT / "data/preview"
    raw = ROOT / "data/cutouts"
    output.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    grid, size = make_grid(ra, dec)
    arrays, frames = [], []
    for index, row in enumerate(selected):
        url = row["access_url"] + "?" + urlencode({"center": f"{ra},{dec}", "size": "0.1"})
        path = raw / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".fits")
        print(f"Downloading/reading cutout {index + 1}/3...", flush=True)
        download(url, path)
        with fits.open(path, memmap=False) as hdus:
            data = np.asarray(hdus["IMAGE"].data, dtype=float)
            spatial = WCS(hdus["IMAGE"].header, fobj=hdus)
            bad, flags = unusable_mask(hdus["FLAGS"])
            aligned = align_nearest(data, spatial, grid, size, ~bad)
            if not np.isfinite(aligned).any():
                raise ValueError("Cutout has no usable coverage on requested grid")
            spectral = WCS(hdus["IMAGE"].header, fobj=hdus, key="W")
            spectral.sip = None  # Official intro notebook: SIP applies only to spatial WCS.
            x, y = spatial.world_to_pixel(SkyCoord(ra, dec, unit="deg"))
            wave, bandwidth = spectral.pixel_to_world(x, y)
            arrays.append(aligned)
            frames.append({
                "index": index, "observation": row,
                "time_utc": Time(row["t_min"], format="mjd").isot,
                "center_wavelength_um": float(wave.to_value("um")),
                "center_bandwidth_um": float(bandwidth.to_value("um")),
                "fits_path": str(path.relative_to(ROOT)), "cutout_url": url,
                "fits_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "image_shape": list(data.shape),
                "extensions": [h.name for h in hdus],
                "bunit": hdus["IMAGE"].header.get("BUNIT"),
                "masked_flags": flags,
                "usable_grid_fraction": float(np.isfinite(aligned).mean()),
                "image_url": f"/api/preview/frames/{index}",
            })
    low, high = np.nanpercentile(np.stack(arrays), [2, 99.5])
    if high <= low:
        raise ValueError("No display dynamic range")
    sheet = Image.new("RGB", (3 * 360, 440), "#101827")
    draw = ImageDraw.Draw(sheet)
    for index, (array, frame) in enumerate(zip(arrays, frames)):
        rgb = grayscale_rgb(array,np.isfinite(array),low,high)
        image = Image.fromarray(np.flipud(rgb)).resize((348, 348), Image.Resampling.NEAREST)
        image.save(output / f"{index}.png")
        sheet.paste(image, (index * 360 + 6, 62))
        draw.text((index * 360 + 10, 12), frame["time_utc"][:19] + " UTC", fill="white")
        draw.text((index * 360 + 10, 32), f"D6 | center {frame['center_wavelength_um']:.4f} um", fill="white")
    draw.text((10, 420), "SPHEREx DR1 | fixed sky grid | diagnostic only | target identification pending", fill="white")
    sheet.save(output / "contact-sheet.png")
    manifest = {
        "query": report["query"], "frames": frames,
        "grid": {"fov_deg": 0.1, "pixel_arcsec": 6.2, "size_px": size,
                 "orientation": "north up, east left", "header": dict(grid.to_header())},
        "display": {"low": float(low), "high": float(high), "stretch": "shared asinh(10*x)",
                    "units": "MJy/sr", "invalid_color": "neutral gray checkerboard"},
        "warnings": ["Diagnostic previews only; target detection and coordinate epoch unverified.",
                     "Wavelengths may differ; brightness differences are not proven variability.",
                     "Nearest-neighbor display resampling; not suitable for precision photometry.",
                     "Zodiacal model not subtracted; artifact mask is incomplete."],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Prepared {len(frames)} frames: {output}")


if __name__ == "__main__":
    main()
