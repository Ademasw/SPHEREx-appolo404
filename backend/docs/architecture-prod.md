# Runtime architecture and viewer URL v1

The frontend is `backend/frontend`. FastAPI serves the Vite build and `/api`; API errors remain JSON/404 rather than returning the SPA.

The server queries NASA/IPAC IRSA SIA for an enclosing circle around the requested TAN grid. It deduplicates observation identities, downloads cutout prefixes or public-cloud FITS sections, checks units and quality definitions, and uses Astropy celestial and spectral WCS. It aligns numerical data and diagonal variances, retains wavelength/bandwidth maps and nearest-sampled quality bits, stacks visits, and creates display products. PNGs are display-only. Spectrum and difference calculations read NPZ arrays.

The bounded job manager shares active processing for identical requests. Metadata is cached for 24 hours and completed sequences for seven days. Cache keys include the algorithm/release configuration and wavelength-table hashes. `SPHEREX_COLLECTIONS=spherex_dr1,spherex_qr3` selects reviewed collections; restart the process after changing configuration. Unknown schemas fail closed. `SPHEREX_SOURCE=cloud` selects the public-cloud source. Static wavelength tables are reviewed only for the current DR1/QR3 schema.

Each rebuild writes a separate generation and atomically replaces its manifest pointer after success. Existing generations are retained. Frame/visit/mask/numerical links may specify `generation=<32 lowercase hex characters>` to retain a consistent view while refresh runs. Other computed products resolve the currently published generation and use no-cache responses. Configure disk monitoring; automatic generation eviction is not implemented.

The browser manages playback, display controls, URL state and plots. `AdvancedView` embeds the existing explorer in a same-origin iframe. The iframe sends `{type:'archive-state', search:'?...'}` using its own origin. The parent checks both `event.origin` and `event.source`; the iframe preserves unrelated URL settings and the parent ignores old state during a reload. No cross-origin commands are accepted.

## URL contract

`/dashboard/advanced`, `/dashboard/player`, `/dashboard/compare`, `/dashboard/colour` use regular paths. Earlier `/#/dashboard/...` links are migrated on load.

| Parameter | Meaning |
|---|---|
| `v=1` | Optional contract version; unversioned links remain supported |
| `q` | Name or coordinate text; a nonempty q takes priority over ra/dec |
| `ra`, `dec` | Complete ICRS pair in degrees, RA [0,360), Dec [−90,90] |
| `det` | D1–D6, or all (display remains one detector; all requests six manifests) |
| `displayDet` | Selected detector number 1–6 for an all-detector result |
| `fov` | Requested degrees: 0.05, 0.1, 0.2 (3′, 6′, 12′) |
| `bg` | model, median, none |
| `clean`, `smooth` | Explicit true/false |
| `view` | Legacy explorer: visits, frames, compare, difference |
| `frame`, `a`, `b`, `cmp` | Explorer index, comparison indices, side/blink/diff |
| `epoch1`, `epoch2` | Dashboard nearest-visit date selections |
| `label1`, `label2`, `fps` | Dashboard labels and integer playback rate 1–24 |
| `wmin`, `wmax` | Optional selected local wavelength-center interval in μm |

Malformed coordinates/parameters produce an error rather than silently changing the target. The inspector's exposure dropdown and aperture click currently remain local UI state; exact restoration of a clicked spectrum is through its exported API URL and parameters.

Example: `/dashboard/compare?v=1&ra=133.7598&dec=-7.2422&det=D6&fov=0.05&bg=model&epoch1=2025-11-10&epoch2=2026-04-25`.

## Embed

The standalone compact route is `/embed`. It accepts the explorer query contract plus `controls=false` to hide the sidebar. Cross-origin parent access is guarded. By default its CSP permits same-origin embedding. Set `SPHEREX_EMBED_ORIGINS=https://example.org` (comma-separated complete origins, without paths), then restart before embedding on an external site. CORS is unnecessary for displaying the iframe; API requests remain on its own origin.

```html
<iframe title="Apollo 404 SPHEREx field" width="900" height="700"
  src="https://YOUR-APOLLO-HOST/embed?v=1&amp;ra=133.7598&amp;dec=-7.2422&amp;det=D6&amp;fov=0.05&amp;controls=false">
</iframe>
```

The server route and CSP are tested. A browser test from http://127.0.0.1:8002 to the app at port 8001 loaded the real field, two visits and playback without cross-origin parent-access errors. The example still requires the actual deployment hostname and its origin allowlist.

## Dependencies and data credits

Python dependencies are pinned in `requirements-lock.txt`; frontend dependencies are pinned in `package-lock.json`. Docker uses those locks. Astropy/Astroquery/NumPy use BSD licenses; FastAPI and React use MIT, Pillow uses its HPND/MIT-CMU license, Aladin Lite 3.9.2-beta declares LGPL-3.0-or-later. Preserve the dependency license files and Aladin logo/link when distributing the app. No new science library was added. Aladin remains lazily loaded on the landing page.

Data remain attributable to SPHEREx / NASA / JPL / Caltech / IRSA; see [DR1 DOI and credits](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html). Gaia markers originate from ESA Gaia DR3 TAP and AllWISE from IRSA `allwise_p3as_psd`. A catalogue marker is not a SPHEREx source detection. Gaia linear proper-motion propagation omits observer parallax/radial velocity; AllWISE coordinates here remain unpropagated and their exact reference epoch is not supplied. Catalogue failures do not invalidate SPHEREx images.
