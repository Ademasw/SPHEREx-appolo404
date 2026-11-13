# Apollo 404: SPHEREx Sky Blinker

> **404: planet not found... yet.**

Team **Apollo 404** at the **NASA Space Apps Challenge 2026** (November 14-15, 2026), challenge **"Planet X and SPHEREx"** (difficulty: Advanced).

**Status:** planning. No code yet. This file describes what we are building and how we split the work.

---

## The idea

In 1930 Clyde Tombaugh found Pluto by "blinking" between two photographs of the same patch of sky taken on different nights: one dot of light had moved.

NASA's **SPHEREx** mission (observing since May 2025) maps the **whole sky every six months in 102 near-infrared bands** and has imaged more than a billion objects. The same patch of sky is photographed again and again, so anything that moves or changes brightness can be spotted: asteroids, comets, nearby stars, brown dwarfs, maybe even a new planet.

**We are building a blink comparator for the SPHEREx sky.**

## What the challenge asks for

Build a **public web tool** where anyone can:

1. **Enter a sky position** (Right Ascension and Declination).
2. **See a series of SPHEREx images** of that patch, **played like a short video**, so moving or changing objects are easy to spot.
3. It must work on the **test targets**:

| Target | Why it is interesting |
|---|---|
| Barnard's Star | one of the fastest-moving stars on the sky |
| Epsilon Indi B | a pair of brown dwarfs orbiting a star |
| WISE 0855 | fast-moving brown dwarf, RA 08h55m10.831s, Dec -7d14m42.53s |
| RW Aurigae | variable star |
| R Draconis | variable star |

The motions are small, from a fraction of a pixel to a few pixels, so the frames must be **aligned precisely using each image's WCS**, and the **contrast must be chosen well**.

### Optional ideas from the challenge (bonus points)

- Easy to update when new SPHEREx data arrives (query the archive live).
- Creative use of the 102 bands, for example stacking all data per detector array for better signal-to-noise. Extra kudos: **spectra generated on the fly**.
- **Add or subtract** images taken at different times.
- **User-selectable field of view** (bigger field = faster movers visible, but more data to download).
- **Overlay other surveys** (Gaia, WISE), for example with Aladin Lite.
- **Coordinates in the URL**, so the tool can be embedded elsewhere.
- Show **metadata such as contamination flags**.

Full official text: [`docs/challenge-statement.md`](docs/challenge-statement.md) (to be added).

---

## How it will look (draft)

```
┌──────────────────────────────────────────────────────────────┐
│ ◉ APOLLO 404   planet not found... yet                       │
├──────────────────────────────────────────────────────────────┤
│ [ Barnard's Star  or  133.7951 -7.2451 ]  [Search]           │
│ Try: (Barnard's Star) (Eps Indi B) (WISE 0855) (RW Aur) (R Dra)│
│ Detector: D1 D2 [D3] D4 D5 D6     FOV: 0.05° [0.1°] 0.25°    │
├────────────────────────────────────┬─────────────────────────┤
│                                    │ Frame 12 / 84           │
│        [ image / animation ]       │ date and time (UTC)     │
│          ⊕ target crosshair        │ detector, wavelength    │
│                                    │ flags summary           │
├────────────────────────────────────┴─────────────────────────┤
│ ▶ ❚❚  speed ──●──   ●●●●●───────────●●●●●───────────●●●●     │
│                     epoch 1           epoch 2         epoch 3│
│ Mode: [Flipbook] [Blink first↔last] [Difference] [Epoch stack]│
└──────────────────────────────────────────────────────────────┘
```

- The five test targets are **one click each** (judges will try them first).
- Every view has a shareable URL: `?ra=133.7951&dec=-7.2451&det=D3&fov=0.1`.
- Later: Aladin Lite overlay (Gaia / WISE) and a spectrum of a clicked point.

### Key idea: stack by epoch, then blink

SPHEREx observes each patch in **bursts**: many frames within a few days, then a gap of about six months until the next visit. Inside one burst nothing moves noticeably. So we:

1. **group frames into epochs** (visits),
2. **stack each epoch** to reduce noise,
3. **blink or subtract epochs** to make motion obvious.

SPHEREx uses a linear variable filter: every frame of a source is taken at a slightly different wavelength. Brightness can therefore change between frames even for a constant star. We show the wavelength of every frame, and for variable stars we compare frames at similar wavelengths.

> Expected motions (rough estimates from literature values, to be verified on real data): SPHEREx pixels are about 6.2″, Barnard's Star moves about 10″/yr, so roughly 1-3 pixels over the mission so far.

---

## Architecture (planned)

**Stack:** Python **FastAPI** backend + **React** (Vite) frontend.

```
React (Vite) ──HTTP──> FastAPI ──TAP──> NASA/IPAC IRSA (metadata)
                          │──cutouts──> IRSA (FITS, parallel, with retries)
                          ├─ WCS alignment, contrast, epoch stacking, differences
                          ├─ PNG frames + JSON metadata
                          └─ disk cache (+ precomputed test targets for the demo)
```

- **Data source:** SPHEREx data at **NASA/IPAC IRSA**. Metadata via TAP (`astroquery`), then small **cutouts** instead of full images. Each cutout is a multi-extension FITS file (`IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `EPSF`, `WCS-WAVE`).
- **Always fresh:** we query IRSA live instead of storing a snapshot, so new data releases show up automatically.
- **Do not mix releases:** frames from different processing versions are filtered.
- A query can take tens of seconds, so the API works as a **job + progress polling**.

### API contract (draft, to agree on in the first hour)

```
GET /api/resolve?name=Barnard's Star      → {ra, dec}
GET /api/sequence?ra&dec&det=D3&fov=0.1   → {job_id}
GET /api/jobs/{id}                        → {status, progress, result?}
GET /api/spectrum?ra&dec                  → [{wavelength_um, flux, err, time}]
```

```json
{
  "query": {"ra": 133.7951, "dec": -7.2451, "detector": "D3", "fov_deg": 0.1},
  "release": "QR3",
  "frames": [
    {"index": 0, "time_iso": "2025-05-12T03:14:00Z", "epoch": 0,
     "wavelength_um": 1.94, "image_url": "/api/img/abc/0.png",
     "flags": {"masked_fraction": 0.02}}
  ],
  "epochs": [{"index": 0, "start": "...", "end": "...", "n_frames": 27,
              "stack_url": "/api/img/abc/epoch0.png"}],
  "difference_url": "/api/img/abc/diff_last_first.png",
  "grid": {"center_ra": 133.7951, "center_dec": -7.2451, "pixel_arcsec": 6.2, "size_px": 58}
}
```

*(Values in the example are placeholders, not real data.)*

---

## Team roles

| # | Role | Responsibilities | First milestone (hour 3) |
|---|---|---|---|
| 1 | **Data** | TAP queries, release filtering, parallel download with retries, disk cache, name → coordinates | script lists all frames for WISE 0855 (count, dates, detectors) |
| 2 | **Processing** | WCS alignment to a common grid, contrast stretch, epoch grouping, stacking, differences, wavelength per frame, spectrum | one FITS → good PNG; then an animated GIF where motion is visible |
| 3 | **Backend + deploy** | FastAPI, jobs and progress, image serving, CORS, caching, public deployment, precomputed test targets | endpoint returns mock JSON, hosting chosen |
| 4 | **Frontend** | React player, time slider, modes, detector / FOV selectors, URL parameters, then Aladin Lite and spectrum | player animates mock frames |
| 5 | **Pitch, QA, submission** | mock JSON, README, acknowledgements, branding, testing all five targets as a user, demo video, slides, submission | mock JSON ready, submission and judging rules read |

Roles 1 and 2 carry the biggest risk (if motion is not visible, nothing else matters), so they work closely in the first hours.

## Timeline

| Hours | Goal |
|---|---|
| 0-3 | End-to-end for WISE 0855: query → frames → GIF with visible motion. Frontend player on mock data. |
| 3-18 | Must-haves: all five targets, API connected to UI, public deployment. |
| 18-36 | Extras: epoch stacking, differences, Aladin overlay, spectra, flags. |
| 36-48 | Bug fixes only, demo video, submission. |

## Open decisions

- [ ] Who takes which role
- [ ] Backend hosting (needs Python and some disk for the cache)
- [ ] Frames as pre-rendered PNG (simple, planned for MVP) or raw data with contrast control in the browser

---

## Data and acknowledgements

This project will use data from **SPHEREx**, a NASA mission, obtained from the **NASA/IPAC Infrared Science Archive (IRSA)**. The exact data release DOI and the required IRSA / SPHEREx acknowledgement text will be added here once we start using the data.

Useful documentation:

- IRSA SPHEREx cutouts tutorial: https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts
- SPHEREx cutout service: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html
- SPHEREx data overview: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html
- Aladin Lite (CDS): https://aladin.cds.unistra.fr/AladinLite/
