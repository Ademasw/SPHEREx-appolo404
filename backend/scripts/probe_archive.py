"""Run from repository root: python -m scripts.probe_archive --help."""
import argparse

from app.archive import save_report, search


def main():
    parser = argparse.ArgumentParser(description="Search real SPHEREx metadata; no FITS download")
    parser.add_argument("--ra", type=float, required=True)
    parser.add_argument("--dec", type=float, required=True)
    parser.add_argument("--release", choices=["dr1", "qr3"], default="dr1")
    args = parser.parse_args()
    print("Querying IRSA SIA (one release, wide survey)...", flush=True)
    report = search(args.ra, args.dec, args.release)
    path = save_report(report)
    print(f"Observations: {report['count']}")
    print(f"Detectors: {report['by_detector']}")
    times = [o["t_min"] for o in report["observations"] if o.get("t_min") is not None]
    if times:
        from astropy.time import Time
        print(f"Observation UTC range: {Time(min(times), format='mjd').isot} — "
              f"{Time(max(times), format='mjd').isot}")
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
