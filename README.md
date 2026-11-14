# Apollo 404

FastAPI backend for the NASA Space Apps Planet X and SPHEREx challenge.
The initial milestone is archive feasibility, not a completed image viewer.
The existing team plan is in TEAM.md; the planned frontend is React/Vite.

## Windows setup

Use Python 3.12. If `python` opens the Windows Store, use the full installed
Python executable path to create the environment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the API documentation.
Currently implemented: `/api/health`, `/api/targets`, `/api/preview`,
and `/api/preview/frames/{index}` (three locally prepared diagnostic frames).

## React viewer

Install frontend dependencies and build before starting FastAPI:

```powershell
cd frontend
npm install
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ for the viewer. For frontend development, run
`npm run dev` inside frontend while FastAPI runs on port 8000. Vite proxies
`/api` to FastAPI. The player supports prepared matched-pair/raw observation
sets, play/pause, frame selection, interval, zoom, display contrast, inversion,
source FITS downloads and shareable mode/frame URLs. Changing contrast and
inversion is visual only. Arbitrary coordinate search is not implemented yet.
Missing data are shown as an error, with no synthetic fallback.

## First real-data experiment

The coordinates below come from the challenge's WISE 0855 example. They are
a search seed, not a verified position propagated to SPHEREx observation dates.

```powershell
.\.venv\Scripts\python.exe -m scripts.probe_archive --ra 133.7951292 --dec -7.2451472 --release dr1
.\.venv\Scripts\python.exe -m pytest -q
```

The probe requests metadata only through official IRSA SIA using Astroquery.
It uses one release to avoid mixing processing versions, reports coverage by
detector and observation dates, and saves a timestamped JSON under data/metadata.
An empty result is valid and must not be replaced with simulated observations.
The probe itself does not download images. After generating the metadata report:

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_preview
```

This downloads three D6 cutouts (first, middle and last available observation),
each limited to 25 MiB. Originals are cached in data/cutouts; previews, a contact
sheet and provenance manifest are saved in data/preview. A fixed north-up,
east-left WCS grid and shared asinh display scale are used. Invalid pixels are
purple. The mask excludes selected unusable pixel flags but is not a complete
artifact rejection procedure. SOURCE flags are retained.

These are diagnostic images, not proof of WISE 0855 detection or variability.
Target coordinates have not been propagated to the observing dates. Central
wavelengths can differ; nearest-neighbor resampling is for display only. No
zodiacal model subtraction, PSF matching, photometry or epoch stacking is applied.
FITS originals, observation metadata, cutout URLs, checksums, flags and display
parameters are retained. `/api/preview` returns 404 until preparation succeeds.

## Catalog audit and two-date blink

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_targets
.\.venv\Scripts\python.exe -m scripts.prepare_blink
```

The audit resolves all five identities with SIMBAD (Harvard mirror fallback),
saves original ECSV tables, verifies the J2000 epoch from column metadata and
propagates proper motion to J2026 before checking DR1 point coverage.
Use `--cached-catalog` to reuse the saved tables. This is an estimated fixed
search center, not an apparent position: observer parallax, radial velocity,
binary orbital motion and the full trajectory footprint are not modeled.

The blink uses the first and last previously cached D6 cutouts only if their
central wavelengths agree to within one quarter of the smaller bandwidth.
It also masks grid pixels with wavelength disagreement above that tolerance.
The supplied ZODI model is subtracted after verifying spatial grid agreement.
Both frames use common coverage and one display scale. Outputs are stored in
data/comparison (two PNGs, blink.gif, provenance manifest), served through
`/api/comparison` and `/api/comparison/frames/{index}`. This is diagnostic,
with no PSF matching, complete artifact rejection or confirmed source detection.

## Remaining milestones

1. Verify catalog positions, epochs and motion for all five targets.
2. Inspect actual coverage in DR1/QR3 separately, including deep collections if needed.
3. Download a small number of official cutouts and inspect IMAGE, FLAGS,
   VARIANCE, ZODI, EPSF and spectral WCS.
4. Align spatially and select spectrally comparable observations before animation.
5. Add processing jobs, cached frames and the React viewer.

Keep FITS and rendered files in data/ (excluded from Git); keep provenance and
processing parameters with each result. Deployment needs persistent storage.
Do not use FITS DATE as an observation time without verifying its meaning;
the probe uses archive t_min/t_max (MJD).

## Sources

- https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/
- https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html

Record release DOI and required acknowledgements before submission.
