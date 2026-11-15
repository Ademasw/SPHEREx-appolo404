"""Small metadata-only query based on the official IRSA intro notebook."""
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astroquery.ipac.irsa import Irsa

ROOT = Path(__file__).resolve().parents[1]


def search(ra: float, dec: float, release: str = "dr1") -> dict:
    if not (math.isfinite(ra) and 0 <= ra < 360):
        raise ValueError("RA must be finite and in [0, 360)")
    if not (math.isfinite(dec) and -90 <= dec <= 90):
        raise ValueError("Dec must be finite and in [-90, 90]")
    if release not in {"dr1", "qr3"}:
        raise ValueError("Release must be dr1 or qr3")
    Irsa.TIMEOUT = 120
    rows = Irsa.query_sia(
        pos=(SkyCoord(ra, dec, unit="deg"), 1 * u.arcsec),
        collection=[f"spherex_{release}"],
    )

    def value(row, name):
        v = row[name]
        if np.ma.is_masked(v):
            return None
        if isinstance(v, (float, np.floating)):
            return float(v) if np.isfinite(v) else None
        return str(v)

    fields = ("obs_id", "access_url", "energy_bandpassname", "t_min", "t_max",
              "em_min", "em_max", "obs_collection", "cloud_access")
    observations = [{k: value(row, k) for k in fields if k in rows.colnames}
                    for row in rows]
    observations.sort(key=lambda r: (r.get("t_min") is None, r.get("t_min") or 0))
    return {
        "query": {"ra_deg": ra, "dec_deg": dec, "radius_arcsec": 1,
                  "release": release, "survey": "wide"},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "NASA/IPAC IRSA SIA",
        "count": len(observations),
        "by_detector": dict(Counter(r.get("energy_bandpassname") for r in observations)),
        "notes": ["Point-coverage search, not full-field coverage verification.",
                  "Wavelength bounds describe the image, not the target pixel.",
                  "Target coordinate epoch/proper motion has not been verified."],
        "observations": observations,
    }


def save_report(report: dict) -> Path:
    query = report["query"]
    path = ROOT / "data" / "metadata" / (
        f"{query['ra_deg']:.7f}_{query['dec_deg']:.7f}_{query['release']}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return path
