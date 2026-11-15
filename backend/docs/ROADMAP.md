# Apollo 404 — team plan until submission (v5.1)

Corrected version of the "v5.0 Master Engineering Blueprint". For the team only.
Submission: **Sun 15 Nov, 11:30** (local event). Times below are local (UTC+6).
Russian version: [ROADMAP.ru.md](ROADMAP.ru.md).

## 0. Where we are (branch `develop`)

Working now, verified on real data:

- Search by name (SIMBAD + proper motion) or coordinates; 5 challenge targets one click.
- Live pipeline for any sky position: IRSA SIA (DR1 + QR3) → fast partial cutouts
  (~120 KB/frame) → public cloud copy as fallback on IRSA 503s → ZODI subtraction,
  flag masks, bilinear alignment → visit stacks.
- Viewer: visit stacks, all frames, difference, **Compare 2 dates** (side by side,
  blink A↔B, B−A), predicted-position ring, shareable URLs, progress for new positions.
- Motion matches the catalog: Barnard's Star 10.3″ expected / 9.3″ measured over one
  year; WISE 0855 and Epsilon Indi B consistent. Epsilon Indi B Gaia-checked
  measurement from `dev` (4.29″ vs 4.68″ catalog) is merged as scripts, not yet shown.
- Not done: public deployment, wavelength-matched comparison, deep-field collections,
  colour composite, spectra, moving objects.

## 1. Ground rules

1. `develop` must run at all times. Work on short branches, merge when it works.
2. **One demo path first**: open link → Barnard's Star blinks → Compare → Difference.
   Everything else is a bonus and must not break this path.
3. Every new feature has a go/no-go time. If it is not working by then, it goes to
   "after the hackathon" and we stop.
4. Code freeze **09:30**. After that: bug fixes and submission only.

## 2. What changed from v5.0 and why

| v5.0 item | Decision | Reason |
|---|---|---|
| AWS us-east-1 next to the S3 mirror | **Keep, top priority** | Our measured bottleneck: cloud reads cost ~2.5 MB/frame; from home this is slow, inside us-east-1 it should be fast. Bucket is public, no keys needed |
| `_deep` collections | **Keep, 15 min** | `spherex_dr1_deep`, `spherex_qr3_deep` add frames near the ecliptic poles (e.g. R Dra) |
| QR2 flux corrections | Drop | QR2 is no longer searchable; we only use DR1 + QR3 |
| 1.083 µm helium stripe and "shuttle glow" | **Keep, optional** | Both are real and documented (checked): atmospheric He I emission makes stripes in band 1, and IRSA provides a He emission template (bands 1-2), an auroral template (band 1) and a shuttle-glow template (band 5, glow of the spacecraft in low Earth orbit) for DR1/QR3. Whether the pipeline already subtracts them is not stated; check before subtracting. My earlier "drop" was wrong |
| `CWAVE` 2040×2040 map | Replace | We use the per-detector `WCS-WAVE` lookup table (stored in `app/wavetables/`), checked identical across exposures and releases |
| `DICHROIC`, `EARLY/LATE TRANSIENT` flags | **Resolved** | Real names from the FITS header: `DICHROIC` exists (bit 7; per the docs non-zero only in bands 3-4). Only one `TRANSIENT` flag (bit 0), no EARLY/LATE. Full list in section 5 |
| Crosstalk masks, 5-frame persistence buffer | **Replace with flags** | No need to model them: the pipeline already flags `CROSSTALK`, `PERSIST`, `GHOST`, `GHOST_FPA`, `GHOST_EXT`, `STREAK`, `SNOWBALL`, `BLOOM`, `HALO` per pixel. Add them to an optional "clean" mask and a Pro-mode overlay (1 h) |
| `reproject_adaptive` | Keep current | Bilinear resampling already keeps sub-pixel positions; motion verified |
| False-colour RGB: Blue 0.75–1.62, Green 2.42–3.82, Red 3.83–5.0 µm | **Keep, fixed** | v5.0 skipped D3 (1.6–2.4 µm). New: Blue = D1+D2, Green = D3+D4, Red = D5+D6 |
| "D1+D4, D2+D5, D3+D6 observe simultaneously" | **Correct (checked in data)** | In 1963 of 2014 exposures the same sky point is covered by exactly these pairs, never other combinations. Useful for the colour composite: paired frames share the same time. Still: different detectors = different wavelengths, so adding them gives a broadband image, not a deeper single-band one |
| ZOGY optimal subtraction | Drop | 1–2 days. Our simple difference already shows the black/white dipole |
| Aladin Lite v3 + AllWISE/unWISE HiPS + Gaia | Bonus | Only if time remains after the core items |
| OBSGEO trajectory solver, 5-parameter astrometry | Drop | Research project |
| ePSF / trailed / curve-of-growth photometry, Lomb–Scargle, unit toggles | Replace | **Simple on-the-fly spectrum**: aperture photometry on the frames we already have (each frame knows its wavelength at the target) |
| Cross-matching CatWISE, dust maps | Drop | After the hackathon |
| Explorer / Pro modes | **Keep** | Matches "usable without our explanations" |
| Comet 3I/ATLAS, near-Earth asteroid | **Try, time-boxed** | See workstream F. Comet first: a near-Earth asteroid has large parallax from low Earth orbit |
| RTX 4070 preprocessing | Drop | The work is network-bound, not GPU-bound |
| North Ecliptic Pole deep field as a showpiece | Keep as preset | Cheap once `_deep` collections are in |

## 3. Workstreams

Effort is for one person. "Done" means checked in the browser on real data.

### A. Public deployment on AWS us-east-1 — highest priority

- EC2 in **us-east-1** (same region as `nasa-irsa-spherex`), e.g. t3.medium,
  Ubuntu, 30 GB disk for the cache.
- `git clone` `develop`, Python venv, `npm run build`, `uvicorn` as a systemd service,
  reverse proxy with HTTPS (Caddy). Without a domain: `<ip>.sslip.io` works with Caddy.
- Copy or recompute the precomputed targets (`python -m scripts.precompute`).
- Measure on the server: cutout vs cloud time per frame. If the cloud path is fast
  there, set `SPHEREX_SOURCE=cloud` (no IRSA 503s at all).
- Done: link opens logged out on a phone; 5 targets instant; a new position < 60 s.
- Effort 2–3 h. **Go/no-go 23:00.**

### B. Pipeline quick wins

1. Add `spherex_dr1_deep`, `spherex_qr3_deep` to `COLLECTIONS` (15 min).
2. Precompute 5 targets × D1–D6 so switching wavelength is instant (background, 30–60 min).
3. **Wavelength-matched comparison** for Compare: stack each visit only from frames in
   the wavelength range shared by A and B, show that range. Needed for variable stars
   (RW Aur, R Dra) and for the "Validity" criterion. 2 h.

### C. Judge path and Explorer / Pro

- Default page: Barnard's Star, Compare, blinking, one sentence of explanation.
- Short legend: orange ring = catalog prediction; white/black on difference = brighter/fainter;
  white cores = saturated.
- Explorer (default): search, 5 targets, wavelength presets, play, Compare.
  Pro: detectors, field of view, contrast, all frames, flags, FITS links.
- Quality badge per visit (good / partial / poor) from coverage, frame count, saturation.
- 2–3 h.

### D. Colour composite (Creativity)

- Per visit: Blue = D1+D2, Green = D3+D4, Red = D5+D6 stacks on the same sky grid
  (same position and field ⇒ same grid already). Match visits by date.
- Needs all six detectors computed (B2). Cold brown dwarfs should appear red.
- 2–3 h. Go/no-go 04:00.

### E. Spectrum on the fly ("extra kudos" in the challenge)

- For a target: aperture photometry at the predicted position in every frame of all
  six detectors; plot flux vs wavelength, one colour per visit.
- Errors from `VARIANCE`; saturated stars flagged, not plotted.
- 2 h after B2. Go/no-go 05:00.

### F. Moving objects — comet first (time-boxed)

1. **Check first (by 22:00):** does the archive have SPHEREx frames of 3I/ATLAS?
   Use the IRSA Moving Object Search Tool (MOST) or JPL Horizons positions + SIA queries.
   If no coverage → stop, pick a bright known comet with coverage, or move F to "after".
2. Ephemeris per frame time from JPL Horizons (`astroquery.jplhorizons`), geocentric.
   For a comet > 1 AU away the parallax from low Earth orbit is below one pixel;
   for a near-Earth asteroid it is not, so asteroids stay out of scope.
3. Cutout centred on the predicted position for each frame (today the pipeline uses one
   centre for all frames; this needs a per-frame centre in `cutout_url` and a per-frame
   grid); two views: object-fixed and sky-fixed.
4. 4–6 h total. **Go/no-go 03:00**; if the first frames are not on screen by then, stop.

### G. Epsilon Indi B science panel

- Run `probe_cloud` → `prepare_epsilon` → `measure_epsilon` → `validate_gaia` on the server
  (faster in us-east-1). Show the result when Epsilon Indi B is selected:
  measured 4.29″, catalog 4.68″, Gaia reference stars, limitations.
- Owner: author of the `dev` science scripts. 1–2 h.

### H. Pitch and submission

- 7-slide pptx (local judging), 30 s video with English subtitles, summary, project details,
  "how we used AI and NASA data", references (release DOIs, IRSA/SPHEREx acknowledgement,
  papers). Team leader sends the pptx to the Telegram topic "Presentation".
- Slides show only what works on the public link. v5.0 ideas go on a "Future work" slide.
- Start now, final text after the 09:30 freeze.

## 4. Timeline

| Time | Goal |
|---|---|
| 20:00–23:00 | A deployment; B1; F step 1 (coverage check by 22:00); H outline |
| **23:00** | Checkpoint: public link works with 5 targets |
| 23:00–03:00 | B2 (background), B3, C; F steps 2–3 (go/no-go 03:00) |
| 03:00–06:00 | D colour (go/no-go 04:00), E spectrum (go/no-go 05:00), G |
| 07:00–09:30 | Polish judge path, test on phones, record the 30 s video |
| **09:30** | Code freeze |
| 10:30–11:30 | Final submission on spaceappschallenge.org, pptx to Telegram |

## 5. Verified facts (checked on 14 Nov, 20:00-21:00)

**Flag bits** (from `MSKN*` keywords of a real DR1 file): 0 `TRANSIENT`, 1 `OVERFLOW`,
2 `SUR_ERROR`, 6 `NONFUNC`, 7 `DICHROIC`, 9 `MISSING_DATA`, 10 `HOT`, 11 `COLD`,
12 `FULLSAMPLE`, 14 `PHANMISS`, 15 `NONLINEAR`, 17 `PERSIST`, 19 `OUTLIER`,
20 `CROSSTALK`, 21 `SOURCE` (informational, keep), 22 `GHOST`, 23 `GHOST_FPA`,
24 `GHOST_EXT`, 25 `STREAK`, 26 `BLOOM`, 27 `SNOWBALL`, 28 `HALO`.
We currently mask NONFUNC, MISSING_DATA, HOT, COLD, NONLINEAR, OVERFLOW, SUR_ERROR.

**Detector pairs:** D1+D4, D2+D5, D3+D6 see the same field at the same time
(two focal planes behind a dichroic; pairing measured from 2014 exposures).

**Background templates:** atmospheric He 1.083 µm (bands 1-2), auroral lines (band 1),
shuttle glow (band 5) exist as IRSA products for DR1/QR3 (Archive User Guide). The
Explanatory Supplement PDF did not download (timeouts), so Table 16 and section 2.5.2 are
still unread.

**3I/ATLAS:** **in the archive and visible (checked).** JPL Horizons positions (C/2025 N1) matched against the archive day by day: same-day DR1 images on 25 days, in three groups: 11-16 Aug 2025 (r = 3.1 AU), 8-15 Dec 2025 (r = 2.0 AU, up to 40 images per day), 17 Mar - 6 Apr 2026 (r = 5.1-5.8 AU). Four D2 frames of 9 Dec 2025, cut at the position interpolated to the exposure time, show the comet with coma and tail at the predicted spot, S/N 230-260. Workstream F is feasible; start with December 2025.

**Cloud vs cutout speed:** measured from here (home connection), 8 frames, 8 workers:
cutouts 0/8 (IRSA connection errors at that moment), cloud 8/8 in 14 s. On the EC2
instance run `python -m scripts.bench_sources` and choose `SPHEREX_SOURCE` from the result.

## 6. After the hackathon

ZOGY subtraction, persistence and crosstalk cleaning, ePSF forced photometry,
astrometric solutions with parallax, near-Earth asteroids, catalog cross-matching
(CatWISE, Gaia), dust maps, Aladin Lite overlays, merging the `front` design.
