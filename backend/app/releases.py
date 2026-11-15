"""Reviewed spectral-image releases; unknown processing schemas fail closed.

IRSA DR1 overview explicitly documents DR1 + QR3 as uniformly processed.
New releases require a schema review here before enabling them in the environment.
"""
import hashlib
import json
import os

ALGORITHM_VERSION = "sequence-4"
SOURCE = "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html"
RELEASES = {
    "spherex_dr1": {"name": "SPHEREx DR1", "schema": "dr1-qr3", "doi": "10.26131/IRSA678", "source": SOURCE},
    "spherex_qr3": {"name": "SPHEREx QR3", "schema": "dr1-qr3", "doi": None, "source": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview.html"},
}


def configured_collections(value=None):
    value = os.environ.get("SPHEREX_COLLECTIONS", "spherex_dr1,spherex_qr3") if value is None else value
    collections = tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    if not collections or any(item not in RELEASES for item in collections):
        raise ValueError("SPHEREX_COLLECTIONS must contain reviewed spectral-image releases: " + ", ".join(RELEASES))
    return collections


def fingerprint(collections, wavetable_dir):
    tables = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(wavetable_dir.glob("*")) if path.is_file()}
    value = {"algorithm": ALGORITHM_VERSION, "releases": {key: RELEASES[key] for key in collections}, "wavetables": tables}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:12]
