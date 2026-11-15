"""Compare download speed of the two image sources on this machine.

Run on the deployment server (e.g. EC2 in us-east-1, next to the public
nasa-irsa-spherex bucket) to decide between SPHEREX_SOURCE=auto and cloud:

    python -m scripts.bench_sources                      # 16 frames near Barnard's Star, D3
    python -m scripts.bench_sources --ra 10.68 --dec 41.27 --frames 24 --workers 8

Prints per-frame times and throughput for IRSA cutouts and for the cloud copy.
Files go to a temporary folder; the pipeline cache is not touched.
"""
import argparse
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from app import pipeline
from app.cloudfits import fetch_section
from app.fastfits import fetch_prefix


def timed(function):
    started = time.time()
    try:
        function()
        return time.time() - started, None
    except Exception as error:  # report, do not stop the benchmark
        return time.time() - started, f"{type(error).__name__}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ra", type=float, default=269.4463)
    parser.add_argument("--dec", type=float, default=4.7682)
    parser.add_argument("--det", default="D3", choices=list(pipeline.DETECTORS))
    parser.add_argument("--fov", type=float, default=0.1)
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    rows = [o for o in pipeline.query_observations(args.ra, args.dec)["observations"]
            if o["detector"] == args.det and o.get("cloud_url")][:args.frames]
    print(f"{len(rows)} {args.det} frames at {args.ra} {args.dec}, {args.workers} parallel workers")
    session = requests.Session()
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        jobs = {
            "cutout": lambda i, row: fetch_prefix(pipeline.cutout_url(row, args.ra, args.dec, args.fov),
                                                  folder / f"c{i}.fits", session=session, attempts=1),
            "cloud": lambda i, row: fetch_section(row["cloud_url"], args.ra, args.dec, args.fov,
                                                  folder / f"s{i}.fits", session=session),
        }
        for name, job in jobs.items():
            started = time.time()
            with ThreadPoolExecutor(args.workers) as pool:
                results = list(pool.map(lambda pair: timed(lambda: job(*pair)), enumerate(rows)))
            wall = time.time() - started
            ok = [t for t, error in results if error is None]
            errors = [error for _, error in results if error]
            median = f"{statistics.median(ok):.1f}s" if ok else "-"
            print(f"{name:7s}: {len(ok)}/{len(rows)} ok, median {median} per frame, "
                  f"total {wall:.1f}s, errors {sorted(set(errors)) or 'none'}")


if __name__ == "__main__":
    main()
