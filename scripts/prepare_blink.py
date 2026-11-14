"""Prepare a cautious two-date diagnostic from already downloaded real FITS."""
import json

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image, ImageDraw

from app.archive import ROOT
from app.preview import align_nearest, make_grid, unusable_mask


def main():
    manifest = json.loads((ROOT / "data/preview/manifest.json").read_text(encoding="utf-8"))
    # Only the first/last cached frames: do not include the spectrally different middle frame.
    frames = [manifest["frames"][0], manifest["frames"][-1]]
    a, b = frames
    tolerance = min(a["center_bandwidth_um"], b["center_bandwidth_um"]) * 0.25
    if abs(a["center_wavelength_um"] - b["center_wavelength_um"]) > tolerance:
        raise ValueError("Cached first and last frames are not centrally wavelength-matched")
    grid, size = make_grid(manifest["query"]["ra_deg"], manifest["query"]["dec_deg"])
    arrays, wave_maps = [], []
    for frame in frames:
        with fits.open(ROOT / frame["fits_path"]) as hdus:
            image = hdus["IMAGE"].data.astype(float)
            zodi = hdus["ZODI"].data.astype(float)
            if zodi.shape != image.shape:
                raise ValueError("ZODI shape mismatch; explicit reprojection required")
            source = WCS(hdus["IMAGE"].header, fobj=hdus)
            zodi_wcs = WCS(hdus["ZODI"].header, fobj=hdus)
            yy, xx = np.indices(image.shape)
            # Confirm matching pixel grids before pixel-wise model subtraction.
            zx, zy = zodi_wcs.world_to_pixel(source.pixel_to_world(xx, yy))
            if not (np.allclose(zx, xx, atol=0.01) and np.allclose(zy, yy, atol=0.01)):
                raise ValueError("ZODI WCS differs from IMAGE")
            bad, _ = unusable_mask(hdus["FLAGS"])
            arrays.append(align_nearest(image - zodi, source, grid, size, ~bad))
            spectral = WCS(hdus["IMAGE"].header, fobj=hdus, key="W")
            spectral.sip = None
            wave, _ = spectral.pixel_to_world(xx, yy)
            wave_maps.append(align_nearest(wave.to_value("um"), source, grid, size, ~bad))
    common = np.isfinite(arrays[0]) & np.isfinite(arrays[1])
    # Reject pixels whose wavelengths differ by more than the central bandwidth tolerance.
    common &= np.abs(wave_maps[0] - wave_maps[1]) <= tolerance
    if common.sum() < 25:
        raise ValueError("Insufficient common wavelength-matched pixels")
    arrays = [np.where(common, array, np.nan) for array in arrays]
    low, high = np.nanpercentile(np.stack(arrays), [2, 99.5])
    if high <= low:
        raise ValueError("No display dynamic range")
    output = ROOT / "data/comparison"
    output.mkdir(parents=True, exist_ok=True)
    rendered = []
    for index, (array, frame) in enumerate(zip(arrays, frames)):
        stretch = np.arcsinh(10 * np.clip((array - low) / (high - low), 0, 1)) / np.arcsinh(10)
        pixels = np.uint8(np.nan_to_num(stretch) * 255)
        rgb = np.stack([pixels] * 3, axis=-1)
        rgb[~common] = [45, 35, 55]
        image = Image.fromarray(np.flipud(rgb)).resize((472, 472), Image.Resampling.NEAREST)
        canvas = Image.new("RGB", (496, 560), "#101827")
        canvas.paste(image, (12, 62))
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 12), frame["time_utc"][:19] + " UTC | SPHEREx DR1 D6", fill="white")
        draw.text((12, 32), f"Center {frame['center_wavelength_um']:.5f} um | IMAGE - ZODI", fill="white")
        draw.text((12, 542), "Diagnostic only - target identification pending", fill="white")
        canvas.save(output / f"{index}.png")
        rendered.append(canvas)
    rendered[0].save(output / "blink.gif", save_all=True, append_images=rendered[1:],
                     duration=900, loop=0)
    result = {
        "query": manifest["query"],
        "frames": [{**frame, "image_url": f"/api/comparison/frames/{i}"} for i, frame in enumerate(frames)],
        "grid": manifest["grid"],
        "processing": {"background": "subtracted supplied ZODI model after grid check",
                       "display_low": float(low), "display_high": float(high),
                       "shared_valid_fraction": float(common.mean()),
                       "wavelength_tolerance_um": tolerance,
                       "pixel_wavelength_filter": True, "stretch": "shared asinh(10*x)"},
        "warnings": ["No confirmed target identification or motion measurement.",
                     "ZODI is a model, not a complete background correction.",
                     "No PSF matching or precision photometry; no difference image.",
                     "Nearest-neighbor display only; quality mask remains incomplete."],
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Prepared two-date blink; shared usable grid: {common.mean():.1%}")
    print(output / "blink.gif")


if __name__ == "__main__":
    main()
