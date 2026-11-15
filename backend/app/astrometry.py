"""Reference-position propagation, explicitly excluding observer parallax."""
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time


def propagate(ra, dec, pmra, pmdec, epoch_jyear, target_jyear):
    values = [ra, dec, pmra, pmdec, epoch_jyear, target_jyear]
    if not np.isfinite(values).all():
        raise ValueError("Finite position, proper motion and epochs are required")
    # SIMBAD pmra includes cos(dec), matching Astropy pm_ra_cosdec.
    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg,
                     pm_ra_cosdec=pmra * u.mas / u.yr,
                     pm_dec=pmdec * u.mas / u.yr,
                     obstime=Time(epoch_jyear, format="jyear"), frame="icrs")
    moved = coord.apply_space_motion(new_obstime=Time(target_jyear, format="jyear"))
    return {"ra_deg": float(moved.ra.deg), "dec_deg": float(moved.dec.deg),
            "epoch_jyear": target_jyear,
            "model": "proper_motion_only_no_parallax_or_radial_velocity"}
