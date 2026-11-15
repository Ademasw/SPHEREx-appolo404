"""Epoch stacking: combine all frames of one detector taken during one sky visit.

SPHEREx revisits a sky position in bursts (several frames within days), then
returns about six months later. Within one visit nearby stars do not move
measurably, so the frames of a visit are aligned on a common sky grid and
averaged. This lowers the noise; blinking the stacked visits shows motion.

Frames inside a visit are taken at different wavelengths across the
detector band (linear variable filter), so a stack is a broadband image of
that detector, not a single-wavelength image.
"""
import numpy as np
from astropy.stats import sigma_clip, sigma_clipped_stats


def group_epochs(times_mjd, gap_days=30.0):
    """Split observation times into visits separated by gaps longer than gap_days.

    Returns a list of index lists, in time order.
    """
    times = np.asarray(times_mjd, dtype=float)
    if times.size == 0:
        return []
    order = np.argsort(times)
    groups = [[int(order[0])]]
    for previous, current in zip(order[:-1], order[1:]):
        if times[current] - times[previous] > gap_days:
            groups.append([])
        groups[-1].append(int(current))
    return groups


def align_bilinear(data, source_wcs, target_wcs, size, valid=None, min_weight=0.75):
    """Resample an image onto the target grid with bilinear interpolation.

    Sub-pixel accurate, unlike nearest-neighbor, which matters because the
    motions we look for are about one pixel per year. Invalid source pixels
    are ignored; an output pixel needs at least `min_weight` of its
    interpolation weight on valid pixels, otherwise it is NaN.
    """
    image = np.asarray(data, dtype=float)
    if valid is not None:
        image = np.where(valid, image, np.nan)
    yy, xx = np.indices((size, size))
    sx, sy = source_wcs.world_to_pixel(target_wcs.pixel_to_world(xx, yy))
    finite = np.isfinite(sx) & np.isfinite(sy)
    sx = np.where(finite, sx, -10.0)
    sy = np.where(finite, sy, -10.0)
    x0 = np.floor(sx).astype(int)
    y0 = np.floor(sy).astype(int)
    fx = sx - x0
    fy = sy - y0
    total = np.zeros((size, size))
    weight = np.zeros((size, size))
    for dy in (0, 1):
        for dx in (0, 1):
            w = (fx if dx else 1 - fx) * (fy if dy else 1 - fy)
            xi, yi = x0 + dx, y0 + dy
            inside = finite & (xi >= 0) & (yi >= 0) & (xi < image.shape[1]) & (yi < image.shape[0])
            values = np.full((size, size), np.nan)
            values[inside] = image[yi[inside], xi[inside]]
            ok = np.isfinite(values)
            total += np.where(ok, w * values, 0.0)
            weight += np.where(ok, w, 0.0)
    return np.where(weight >= min_weight, total / np.where(weight > 0, weight, 1), np.nan)


def subtract_background(frame):
    """Remove a constant sky level (sigma-clipped median) from an aligned frame."""
    if not np.isfinite(frame).any():
        return frame
    _, median, _ = sigma_clipped_stats(frame, sigma=3.0, maxiters=5)
    return frame - median


def measure_source(image, x, y, radius=2.5, iterations=3):
    """Flux-weighted centroid of the source nearest to grid pixel (x, y).

    Starts at the given position (for example a catalog prediction) and
    re-centers a few times. Returns x, y and peak signal-to-noise, where the
    noise is the robust (MAD) scatter of the whole image.
    """
    yy, xx = np.indices(image.shape)
    noise = 1.4826 * np.nanmedian(np.abs(image - np.nanmedian(image)))
    for _ in range(iterations):
        inside = ((xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2) & np.isfinite(image)
        weights = np.clip(image[inside], 0, None)
        if not inside.any() or weights.sum() <= 0:
            return None
        x = float((weights * xx[inside]).sum() / weights.sum())
        y = float((weights * yy[inside]).sum() / weights.sum())
    peak = float(np.nanmax(image[inside]))
    return {"x": x, "y": y, "peak_snr": peak / noise if noise > 0 else None}


def aperture_photometry(image, variance, x, y, radius=3.0):
    """Simple aperture sum and propagated variance at a predicted position."""
    yy, xx = np.indices(image.shape)
    aperture = ((xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2)
    valid = aperture & np.isfinite(image) & np.isfinite(variance) & (variance > 0)
    if not valid.any():
        return None
    flux = float(np.sum(image[valid]))
    error = float(np.sqrt(np.sum(variance[valid])))
    return {"flux": flux, "error": error, "snr": flux / error if error else None,
            "pixels": int(valid.sum()), "radius_px": radius}


def combine(cube, variance=None, sigma=4.0):
    """Inverse-variance weighted mean along axis 0 with per-pixel sigma clipping.

    Clipping removes cosmic rays, satellite trails and other one-frame
    outliers. The spread is estimated with the median absolute deviation,
    because with ~10 frames a single outlier inflates a plain standard
    deviation enough to survive the clip. Returns (stacked image, number of
    frames used per pixel).
    """
    cube = np.asarray(cube, dtype=float)
    good = np.isfinite(cube)
    if cube.shape[0] >= 3:
        clipped = sigma_clip(cube, sigma=sigma, maxiters=3, axis=0, masked=True,
                             cenfunc="median", stdfunc="mad_std")
        good &= ~np.ma.getmaskarray(clipped)
    if variance is None:
        weights = good.astype(float)
    else:
        variance = np.asarray(variance, dtype=float)
        usable = good & np.isfinite(variance) & (variance > 0)
        weights = np.where(usable, 1.0 / np.where(usable, variance, 1.0), 0.0)
    total = weights.sum(axis=0)
    stacked = np.where(total > 0, (weights * np.nan_to_num(cube)).sum(axis=0) / np.where(total > 0, total, 1), np.nan)
    return stacked, (weights > 0).sum(axis=0)
