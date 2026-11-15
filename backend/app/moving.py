"""Ephemeris access for moving-object searches.

Horizons is optional at install time.  When unavailable, the API returns a
clear dependency error rather than silently treating a moving object as fixed.
"""
from datetime import datetime


def horizons_ephemeris(target: str, start: str, stop: str, step: str = "1d"):
    try:
        from astroquery.jplhorizons import Horizons
    except ImportError as error:
        raise RuntimeError("astroquery is required for moving-object ephemerides") from error
    try:
        start_date = datetime.fromisoformat(start.replace("Z", "+00:00")).date().isoformat()
        stop_date = datetime.fromisoformat(stop.replace("Z", "+00:00")).date().isoformat()
        table = Horizons(id=target, location="500@399", epochs={"start": start_date,
                          "stop": stop_date, "step": step}).ephemerides()
    except Exception as error:
        raise RuntimeError(f"Horizons lookup failed: {type(error).__name__}") from error
    return [{"time_utc": str(row["datetime_str"]), "ra_deg": float(row["RA"]),
             "dec_deg": float(row["DEC"]), "target": target} for row in table]


def archive_matches(points, release="dr1"):
    """Probe IRSA coverage at each ephemeris point and retain matching rows."""
    from app.archive import search
    matches = []
    for point in points:
        report = search(point["ra_deg"], point["dec_deg"], release=release)
        if report["observations"]:
            matches.append({"ephemeris": point, "observations": report["observations"]})
    return matches
