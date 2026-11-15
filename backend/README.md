# Apollo 404

A blink comparator for the SPHEREx sky (NASA Space Apps 2026, "Planet X and
SPHEREx"). Type any sky position or object name; the app fetches every
SPHEREx image of that spot from the NASA/IPAC IRSA archive, aligns them, stacks
each visit and plays them in time, so moving or changing objects stand out.
Nothing is downloaded in advance: any position is processed on request
(typically 30-60 s the first time, instant afterwards from the cache).

Project status and scientific reports (Russian): [PROJECT_STATUS.md](PROJECT_STATUS.md),
[docs/delivery-report.md](docs/delivery-report.md).

## Windows setup

Use Python 3.12. If `python` opens the Windows Store, use the full installed
Python executable path to create the environment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the API documentation.

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
`/api` to FastAPI. The viewer has a search box (object name, decimal degrees
or sexagesimal), one-click challenge targets, detector (D1-D6) and field of
view (3', 6', 12') selectors, three modes (visit stacks, all frames,
last-minus-first difference), a predicted-position ring for catalog objects,
zoom/contrast/invert and shareable URLs such as
`/?q=Barnard%27s%20Star&det=D6&fov=0.1&view=visits`. Contrast and inversion
change the picture only. Missing data are shown as an error, never simulated.

## How the live pipeline works (app/pipeline.py)

1. **Find images.** IRSA SIA query for the position in `spherex_dr1` and
   `spherex_qr3` (QR3 continues DR1 in time, May-Oct 2026, so both are used;
   all images share processing version 7.0.5). Cached for a day.
2. **Download only what is needed.** Each IRSA cutout is a FITS file whose
   EPSF (PSF model) table is 3.9 MB of a 4 MB file. `app/fastfits.py` reads
   the stream only until IMAGE, FLAGS, VARIANCE and ZODI are complete
   (~120 KB) and closes the connection: about 2.5 s instead of 17 s per frame.
   Wavelengths come from the WCS-WAVE lookup table, which is identical for
   every exposure of a detector (checked across DR1 and QR3) and stored once
   per detector in `app/wavetables/` (`python -m scripts.fetch_wavetables`).
3. **Be robust to a busy archive.** IRSA currently answers 503 to a large,
   random share of cutout requests. Downloads run 8 in parallel with two quick
   tries each; a frame that still fails is read from NASA's public cloud copy
   of the same image (`app/cloudfits.py`, bucket `nasa-irsa-spherex`, plain
   HTTPS, no AWS account). HTTP range requests fetch only the headers and the
   needed rows, including rows of the RICE-compressed FLAGS layer; the pixels
   are identical to the cutout (checked to 1e-14). The cloud path reads about
   2.5 MB per frame (full-width rows), so it is the fallback, not the default;
   set `SPHEREX_SOURCE=cloud` to use it only, e.g. if the cutout service is
   down. At most 16 frames per visit and a 40 s budget, after which the
   pipeline continues with what arrived (failures are listed).
4. **Process.** IMAGE minus ZODI model; unusable FLAGS masked; saturated
   cores (OVERFLOW/SUR_ERROR) drawn white; bilinear resampling onto one fixed
   north-up sky grid; sky level removed.
5. **Visits.** Frames closer than 30 days form a visit; each visit is an
   inverse-variance weighted mean with per-pixel MAD sigma clipping. Visits
   with fewer than 5 frames are skipped when at least two better ones exist.
6. **Output.** PNG per frame and per visit, last-minus-first difference,
   blink GIF and manifest.json in `data/sequences/<ra>_<dec>_<fov>/<detector>/`.

Names are resolved with SIMBAD including proper motion; the search center is
moved to 2026.0 and per-visit predicted positions are drawn as a ring.

API: `GET /api/sequence?q=<name or coordinates>&det=D6&fov=0.1` (or `ra=&dec=`)
returns 200 with the manifest, or 202 with `stage`/`done`/`total` while the
job runs; poll the same URL. `GET /api/resolve?q=` resolves input only.
Precompute the demo targets with `python -m scripts.precompute`.

Verified on real data: WISE 0855 (D6) shows a source at the predicted
position in both well-covered visits; the measured shift between Nov 2025 and
Apr 2026 matches the catalog proper motion (0.54 vs 0.58 px). Barnard's Star's
northward motion is obvious in the difference image.

## Earlier experiments (kept for reference)

### First real-data experiment

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

### Catalog audit and two-date blink

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

## Implemented roadmap extensions

The on-demand pipeline now searches the DR1/QR3 wide and deep collections,
supports a Pro artifact mask, and the precompute command defaults to all six
detectors. Prepared sequences expose:

- `/api/science/{sequence-key}/quality` for coverage-based visit badges;
- `/api/science/{sequence-key}/matched` for the shared wavelength interval of two visits;
- `/api/science/{sequence-key}/spectrum` for variance-weighted aperture measurements;
- `/api/science/{sequence-key}/colour/{visit}.png` for D1+D2 / D3+D4 / D5+D6 RGB;
- `/api/moving/ephemeris` for JPL Horizons positions, including 3I/ATLAS (`C/2025 N1`).

These are explicitly exploratory products: flux is not calibrated, saturated
points are omitted from spectra, and the quality badge is not a scientific
validity score. AWS deployment remains intentionally outside this repository.

## Remaining milestones

1. Public deployment with persistent disk for data/ (cache).
2. Optional: Aladin Lite overlay (Gaia, WISE), spectra, light curves.

## Science validation: Epsilon Indi B and Barnard's Star (scripts)

These analyses read official cloud copies of the SPHEREx images (public
`nasa-irsa-spherex` bucket on AWS, plain HTTPS, no AWS account needed): IRSA
SIA returns their location in `cloud_access`, and Astropy/fsspec reads only the
needed FITS sections, which avoids the cutout service's 503 errors.

- Epsilon Indi B, D3: two observations from April 2025 and April 2026 with
  close wavelengths. `python -m scripts.probe_cloud`, then
  `python -m scripts.prepare_epsilon` (docs/epsilon-comparison.md).
- Photocentre measurement on the original pixels with a field-shift correction:
  `python -m scripts.measure_epsilon` (docs/epsilon-motion-result.md), served at
  `/api/epsilon/motion`.
- Gaia DR3 check of the reference stars, with their own proper motions removed:
  `python -m scripts.validate_gaia` (docs/gaia-validation.md). Current
  preliminary result: 4.29" (east +3.31", north -2.74") against 4.68" predicted
  from the catalog proper motion; PSF, blending and parallax not yet modelled.
- Barnard's Star source inspection: `python -m scripts.inspect_barnard`, then
  `python -m scripts.prepare_barnard_view` (docs/barnard-inspection.md),
  served at `/api/barnard`.

Missing measurements are never filled with generated values
(docs/data-gap-fix.md).

### Cloud-based coordinate jobs (`/api/jobs`)

`POST /api/jobs` with RA/Dec, field size (1.2-6 arcmin) and detector reads up
to three observations from the cloud copies; `GET /api/jobs/{id}` reports
progress, `/api/jobs/{id}/result` and `/api/jobs/{id}/frames/{index}` serve the
result (24 h cache, two workers, four queue slots). Implemented in
`app/cloud_jobs.py`. The main viewer uses `/api/sequence` (above), which
covers all frames, both releases and visit stacks.

Keep FITS and rendered files in data/ (excluded from Git); keep provenance and
processing parameters with each result. Deployment needs persistent storage.
Do not use FITS DATE as an observation time without verifying its meaning;
the probe uses archive t_min/t_max (MJD).

## Sources

- https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/
- https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html

Record release DOI and required acknowledgements before submission.
