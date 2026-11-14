"""Diagnostic WCS-aligned previews; not photometry or a discovery product."""
import numpy as np
from astropy.wcs import WCS


def make_grid(ra, dec, fov_deg=0.1, pixel_arcsec=6.2):
    size = int(np.ceil(fov_deg * 3600 / pixel_arcsec))
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [(size + 1) / 2, (size + 1) / 2]
    wcs.wcs.cdelt = [-pixel_arcsec / 3600, pixel_arcsec / 3600]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs, size


def align_nearest(data, source_wcs, target_wcs, size, valid=None):
    """Nearest-neighbor display resampling. No flux/error propagation claimed."""
    yy, xx = np.indices((size, size))
    sky = target_wcs.pixel_to_world(xx, yy)
    sx, sy = source_wcs.world_to_pixel(sky)
    finite = np.isfinite(sx) & np.isfinite(sy)
    ix = np.rint(np.where(finite, sx, -1)).astype(int)
    iy = np.rint(np.where(finite, sy, -1)).astype(int)
    inside = finite & (ix >= 0) & (iy >= 0) & (ix < data.shape[1]) & (iy < data.shape[0])
    result = np.full((size, size), np.nan)
    y, x = np.where(inside)
    good = np.isfinite(data[iy[y, x], ix[y, x]])
    if valid is not None:
        good &= valid[iy[y, x], ix[y, x]]
    result[y[good], x[good]] = data[iy[y[good], x[good]], ix[y[good], x[good]]]
    return result


def unusable_mask(hdu):
    """Conservative diagnostic mask, names read from this release's header.

    SOURCE is informational and must not be removed. Other artifact flags are
    retained for inspection; this is not a complete science-quality selection.
    """
    names = {"NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR", "OVERFLOW", "SUR_ERROR"}
    bits = 0
    used = []
    for key in hdu.header:
        if key.startswith("MSKN") and hdu.header[key] in names:
            bits |= 1 << int(key[4:])
            used.append(hdu.header[key])
    if not used:
        raise ValueError("No recognized quality flag definitions; inspect FITS before rendering")
    return (hdu.data.astype(np.int64) & bits) != 0, used
