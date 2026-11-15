"""Gaia DR3 astrometry for target overlays and proper-motion propagation."""
from __future__ import annotations

import functools
import io
import math

import numpy as np
import requests
from astropy.table import Table
from astropy.coordinates import SkyCoord
import astropy.units as u

from app.astrometry import propagate

TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"
SEARCH_RADIUS_DEG = 0.2
MATCH_RADIUS_ARCSEC = 5.0
RUWE_LIMIT = 1.4


def _number(row, name):
    value = row[name]
    if np.ma.is_masked(value):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


@functools.lru_cache(maxsize=256)
def match(ra_deg: float, dec_deg: float, epoch: float = 2026.0) -> dict | None:
    """Find and propagate the closest Gaia DR3 source.

    The search cone is wider than the final match radius so high-proper-motion
    sources can be found at their Gaia reference-epoch positions. RUWE is
    required for using the source as a propagation reference.
    """
    query = f"""
      SELECT TOP 1000 source_id, ra, dec, ref_epoch, pmra, pmdec,
             parallax, ruwe, phot_g_mean_mag
      FROM gaiadr3.gaia_source
      WHERE 1 = CONTAINS(POINT('ICRS', ra, dec),
                         CIRCLE('ICRS', {float(ra_deg)}, {float(dec_deg)}, {SEARCH_RADIUS_DEG}))
        AND pmra IS NOT NULL AND pmdec IS NOT NULL
    """
    try:
        response = requests.post(
            TAP_URL,
            data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "votable", "QUERY": query},
            timeout=(3, 8),
        )
        response.raise_for_status()
        table = Table.read(io.BytesIO(response.content), format="votable")
    except Exception:
        return None
    if len(table) == 0:
        return None
    # TAP can return a syntactically valid VOTable containing an error/status
    # result instead of Gaia rows. Treat that exactly like an unavailable
    # Gaia match so the normal SIMBAD path can continue.
    columns = {name.lower() for name in table.colnames}
    if not {"source_id", "ra", "dec", "ref_epoch", "pmra", "pmdec", "ruwe"}.issubset(columns):
        return None
    names = {name.lower(): name for name in table.colnames}

    target = SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame="icrs")
    candidates = []
    for row in table:
        ra = _number(row, names["ra"])
        dec = _number(row, names["dec"])
        pmra = _number(row, names["pmra"])
        pmdec = _number(row, names["pmdec"])
        ref_epoch = _number(row, names["ref_epoch"]) or 2016.0
        if None in (ra, dec, pmra, pmdec):
            continue
        try:
            moved = propagate(ra, dec, pmra, pmdec, ref_epoch, epoch)
            separation = target.separation(SkyCoord(moved["ra_deg"] * u.deg, moved["dec_deg"] * u.deg)).arcsec
        except Exception:
            continue
        ruwe = _number(row, names["ruwe"])
        candidates.append({
            "source_id": str(row[names["source_id"]]),
            "ra_deg": ra,
            "dec_deg": dec,
            "predicted_ra_deg": moved["ra_deg"],
            "predicted_dec_deg": moved["dec_deg"],
            "pmra_mas_yr": pmra,
            "pmdec_mas_yr": pmdec,
            "parallax_mas": _number(row, names["parallax"]) if "parallax" in names else None,
            "ruwe": ruwe,
            "g_mag": _number(row, names["phot_g_mean_mag"]) if "phot_g_mean_mag" in names else None,
            "ref_epoch": ref_epoch,
            "propagation_epoch": epoch,
            "separation_arcsec": float(separation),
            "quality_ok": ruwe is not None and ruwe < RUWE_LIMIT,
        })
    candidates.sort(key=lambda item: (item["separation_arcsec"], not item["quality_ok"]))
    return candidates[0] if candidates and candidates[0]["separation_arcsec"] <= MATCH_RADIUS_ARCSEC else None
