"""Conservative diagnostic source checks, not calibrated astrometry."""
import numpy as np


def inspect_source(image, variance, valid, x, y, radius=3):
    """Report a local signal candidate without substituting a catalog prediction.

    Peak S/N uses the supplied per-pixel variance and an annular median background.
    This is not integrated source S/N, a significance test, or a motion measurement.
    """
    yy, xx = np.indices(image.shape)
    r2 = (xx-x)**2+(yy-y)**2
    finite = valid & np.isfinite(image) & np.isfinite(variance) & (variance > 0)
    aperture = r2 <= radius**2
    core = r2 <= 1.5**2
    annulus = (r2 >= (radius+1)**2) & (r2 <= (radius+4)**2) & finite
    if not annulus.any() or not (aperture & finite).any():
        return {'status':'insufficient_data'}
    background = float(np.median(image[annulus]))
    local_snr = np.where(aperture & finite, (image-background)/np.sqrt(np.where(variance>0,variance,np.nan)), -np.inf)
    py, px = np.unravel_index(np.nanargmax(local_snr), image.shape)
    peak_snr = float(local_snr[py,px])
    core_fraction = float(finite[core].mean()) if core.any() else 0.0
    return {'status':'signal_candidate' if peak_snr >= 5 and core_fraction >= .8 else 'not_reliable',
            'peak_pixel':[int(px),int(py)], 'peak_pixel_snr':peak_snr,
            'background_median':background, 'valid_core_fraction':core_fraction,
            'peak_distance_from_prediction_px':float(np.hypot(px-x,py-y)),
            'method':'local peak / supplied pixel uncertainty; no centroid or motion fit'}
