"""Turn user input into a sky position: decimal degrees, sexagesimal, or an object name.

Names are resolved with SIMBAD including proper motion. Catalog positions are
for epoch J2000; fast-moving nearby stars have moved by arcminutes since, so
the search center is propagated to EPOCH (the middle of the SPHEREx data)
and the proper motion is kept for per-visit predicted positions.
"""
import json
import re
import threading

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord

from app.astrometry import propagate
from app.targets import TARGETS

from app.pipeline import DATA

EPOCH = 2026.0
CACHE = DATA / "resolve_cache.json"
_lock = threading.Lock()


class ResolveError(Exception):
    pass


def _cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _store(key, value):
    with _lock:
        cache = _cache()
        cache[key] = value
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def _simbad(name):
    from astroquery.simbad import Simbad
    last = None
    for server in (None, "simbad.harvard.edu"):  # official mirror if CDS is down
        try:
            service = Simbad()
            if server:
                service.server = server
            service.TIMEOUT = 30
            service.add_votable_fields("pmra", "pmdec")
            table = service.query_object(name)
            if table is None or len(table) == 0:
                raise ResolveError(f"SIMBAD does not know '{name}'")
            row = table[0]
            names = {c.lower(): c for c in table.colnames}

            def value(column):
                v = row[names[column]] if column in names else None
                return None if v is None or np.ma.is_masked(v) or not np.isfinite(float(v)) else float(v)

            main_id = row[names["main_id"]] if "main_id" in names else name
            return {"name": str(main_id).strip() or name, "ra2000": value("ra"), "dec2000": value("dec"),
                    "pmra": value("pmra"), "pmdec": value("pmdec"), "source": "SIMBAD"}
        except ResolveError:
            raise
        except Exception as error:
            last = error
    raise ResolveError(f"Name lookup failed ({type(last).__name__}); enter RA and Dec instead")


def _with_position(info):
    if info.get("ra2000") is None or info.get("dec2000") is None:
        raise ResolveError("Lookup returned no coordinates")
    if info.get("pmra") is not None and info.get("pmdec") is not None:
        moved = propagate(info["ra2000"], info["dec2000"], info["pmra"], info["pmdec"], 2000.0, EPOCH)
        info["ra_deg"], info["dec_deg"] = moved["ra_deg"], moved["dec_deg"]
        info["position_epoch"] = EPOCH
    else:
        info["ra_deg"], info["dec_deg"] = info["ra2000"], info["dec2000"]
        info["position_epoch"] = 2000.0
    return info


def parse_coordinates(text):
    """Return (ra, dec) in degrees for coordinate-looking input, else None."""
    cleaned = text.strip().replace(",", " ")
    numbers = re.fullmatch(r"\s*([+-]?\d+(?:\.\d*)?)\s+([+-]?\d+(?:\.\d*)?)\s*", cleaned)
    if numbers:
        ra, dec = float(numbers.group(1)), float(numbers.group(2))
    elif re.search(r"\d", cleaned) and re.search(r"[hms:°d]", cleaned) and not re.search(r"[a-ce-gi-ln-rt-zA-Z]{2,}", cleaned):
        try:
            coord = SkyCoord(cleaned, unit=(u.hourangle, u.deg))
        except Exception:
            try:
                coord = SkyCoord(cleaned, unit=(u.deg, u.deg))
            except Exception:
                return None
        ra, dec = float(coord.ra.deg), float(coord.dec.deg)
    else:
        return None
    if not (0 <= ra < 360 and -90 <= dec <= 90):
        raise ResolveError("RA must be in [0, 360) and Dec in [-90, 90] degrees")
    return ra, dec


def resolve(text):
    """Resolve user input; returns a dict with ra_deg, dec_deg and optional name/proper motion."""
    text = (text or "").strip()
    if not text:
        raise ResolveError("Enter coordinates or an object name")
    if len(text) > 100:
        raise ResolveError("Input too long")
    coords = parse_coordinates(text)
    if coords:
        return {"name": None, "ra_deg": coords[0], "dec_deg": coords[1], "source": "coordinates"}
    key = text.lower()
    target = next((t for t in TARGETS if key in (t["id"], t["name"].lower(), t["catalog_query"].lower())), None)
    query = target["catalog_query"] if target else text
    cached = _cache().get(query.lower())
    if cached is None:
        cached = _simbad(query)
        _store(query.lower(), cached)
    info = _with_position(dict(cached))
    if target:
        info["id"], info["name"] = target["id"], target["name"]
    return info
