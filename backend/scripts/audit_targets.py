"""Resolve catalog identities and inspect SPHEREx coverage, without downloading FITS."""
import json
import argparse
from datetime import datetime, timezone

import numpy as np
from astroquery.simbad import Simbad
from astropy.table import Table

from app.archive import ROOT, save_report, search
from app.targets import TARGETS
from app.astrometry import propagate


def scalar(value):
    if np.ma.is_masked(value):
        return None
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached-catalog", action="store_true")
    args = parser.parse_args()
    service = Simbad()
    service.TIMEOUT = 90
    if not args.cached_catalog:
        try:
            service.add_votable_fields("pmra", "pmdec", "plx_value", "coo_bibcode", "pm_bibcode")
        except Exception:
            # Official Harvard mirror if the CDS TAP service is unavailable.
            service = Simbad()
            service.server = "simbad.harvard.edu"
            service.TIMEOUT = 90
            service.add_votable_fields("pmra", "pmdec", "plx_value", "coo_bibcode", "pm_bibcode")
    output = ROOT / "data/catalog"
    output.mkdir(parents=True, exist_ok=True)
    audit = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "targets": []}
    for target in TARGETS:
        entry = dict(target)
        print(f"Resolving {target['name']}...", flush=True)
        try:
            cached = output / f"{target['id']}.ecsv"
            table = Table.read(cached, format="ascii.ecsv") if args.cached_catalog else service.query_object(target["catalog_query"])
            if table is None or len(table) != 1:
                raise ValueError("Expected one unambiguous SIMBAD match")
            table.write(output / f"{target['id']}.ecsv", format="ascii.ecsv", overwrite=True)
            entry["catalog"] = {name: scalar(table[0][name]) for name in table.colnames}
            ra, dec = float(table[0]["ra"]), float(table[0]["dec"])
            epoch_metadata = table["ra"].meta.get("utype", "")
            if "CT.epoch=J2000" not in epoch_metadata:
                raise ValueError("Catalog reference epoch is not explicitly J2000")
            position = propagate(ra, dec, float(table[0]["pmra"]), float(table[0]["pmdec"]), 2000.0, 2026.0)
            entry["reference_epoch_jyear"] = 2000.0
            entry["epoch_evidence"] = epoch_metadata
            entry["search_position"] = position
            ra, dec = position["ra_deg"], position["dec_deg"]
            entry["position_status"] = "proper_motion_estimate_at_J2026"
            entry["warnings"] = [
                "J2000 epoch verified from SIMBAD column metadata; propagated to J2026.",
                "Coverage query uses one fixed reference position, not the full moving trajectory.",
                "Parallax and radial velocity are not applied; not an apparent observer position.",
            ]
            print(f"Querying DR1 at catalog position {ra:.7f}, {dec:.7f}...", flush=True)
            report = search(ra, dec)
            path = save_report(report)
            times = [r["t_min"] for r in report["observations"] if r.get("t_min") is not None]
            entry["coverage"] = {"count": report["count"], "by_detector": report["by_detector"],
                                 "t_min_mjd": min(times) if times else None,
                                 "t_max_mjd": max(times) if times else None,
                                 "report_path": str(path.relative_to(ROOT))}
            print(f"Found {report['count']} observations", flush=True)
        except Exception as error:
            entry["error"] = f"{type(error).__name__}: {error}"
            print(entry["error"], flush=True)
        audit["targets"].append(entry)
        (output / "audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Saved audit: {output / 'audit.json'}")
    if any("error" in item for item in audit["targets"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
