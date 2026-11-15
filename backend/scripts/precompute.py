"""Precompute sequences so the demo targets open instantly.

    python -m scripts.precompute                      # five challenge targets, D1-D6
    python -m scripts.precompute --detectors D2 D6    # several detectors
    python -m scripts.precompute --q "133.7951 -7.2451"

Uses the same pipeline as the web API (app.pipeline), so results are found
by the viewer without any extra step.
"""
import argparse
import time

from app import pipeline
from app.resolve import resolve
from app.targets import TARGETS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", nargs="*", help="names or coordinates; default: the five challenge targets")
    parser.add_argument("--detectors", nargs="*", default=list(pipeline.DETECTORS), choices=list(pipeline.DETECTORS))
    parser.add_argument("--fov", type=float, default=0.1, choices=list(pipeline.FOVS))
    args = parser.parse_args()
    queries = args.q or [t["name"] for t in TARGETS]
    failed = 0
    for query in queries:
        info = resolve(query)
        ra, dec = round(info["ra_deg"], 4) % 360, round(info["dec_deg"], 4)
        target = info if info.get("pmra") is not None else None
        for detector in args.detectors:
            started = time.time()
            try:
                manifest = pipeline.run(ra, dec, detector, args.fov, target=target)
                visits = manifest["visits"]
                print(f"{query} {detector}: {len(manifest['frames'])} frames, {len(visits)} visits, "
                      f"{manifest['processing']['frames_failed']} failed, {time.time() - started:.0f}s")
                for visit in visits:
                    m = visit.get("measured_position")
                    p = visit.get("predicted_position")
                    extra = (f" predicted ({p['grid_pixel']['x']:.2f}, {p['grid_pixel']['y']:.2f})"
                             f" measured ({m['x']:.2f}, {m['y']:.2f}) S/N {m['peak_snr']:.1f}") if m and p else ""
                    print(f"    {visit['time_utc'][:10]} {visit['n_frames']} frames{extra}")
            except pipeline.PipelineError as error:
                failed += 1
                print(f"{query} {detector}: {error}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
