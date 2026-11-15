# Front — Planet X & SPHEREx Explorer

React + Vite frontend for the NASA Space Apps Challenge.

## Quick start

```bash
cd front
npm install
npm run dev        # http://localhost:5173
npm run build      # production build -> dist/
```

> On Windows PowerShell, if `npm` is blocked by the execution policy, use `npm.cmd` instead.

## Pages

| Route                | Page                                          | Cursor trail |
| -------------------- | --------------------------------------------- | ------------ |
| `/`                  | Landing (hero, orbits, stars)                 | ON           |
| `/dashboard/player`  | Dashboard — View Mode A (sequence player)     | OFF          |
| `/dashboard/compare` | Dashboard — View Mode B (side-by-side epochs) | OFF          |

## Project structure

```
front/
├─ index.html                  # Google Fonts <link> (change fonts here + typography.css)
├─ scripts/
│  └─ generate-placeholders.mjs  # creates placeholder PNGs (never overwrites yours)
└─ src/
   ├─ main.jsx                 # entry: BrowserRouter + global styles
   ├─ App.jsx                  # global animated background + router
   ├─ assets/                  # ALL images live here
   │  └─ index.js              # the only file that imports images -> ASSETS object
   ├─ config/
   │  ├─ animation.js          # cursor trail, star field, player speeds
   │  └─ project.js            # project / team name placeholders
   ├─ router/
   │  ├─ AppRouter.jsx         # routes + page transitions
   │  └─ routes.js             # route path constants
   ├─ hooks/
   │  └─ useCursorTrail.js     # PNG star-trail logic
   ├─ components/
   │  ├─ background/           # AnimatedBackground, StarField, OrbitalSystem
   │  ├─ cursor/CursorTrail.jsx
   │  ├─ layout/               # Header, PageTransition
   │  └─ media/MediaPlayer.jsx # play/pause + timeline (image sequence or video)
   ├─ pages/
   │  ├─ LandingPage/
   │  └─ Dashboard/            # Dashboard (layout), Sidebar, PlayerView, CompareView
   └─ styles/
      ├─ theme.css             # colours + CSS animation speeds
      ├─ typography.css        # ALL font families / sizes / weights / spacing
      └─ global.css            # reset
```

## Swapping assets

Drop your PNGs into `src/assets/` using the **same file names** (`logo.png`, `planet1.png`,
`star-particle.png`, …) — done. To use new names, edit `src/assets/index.js`.

`npm run placeholders` regenerates any missing placeholder images; it skips files that already exist.

## Tuning cheat-sheet

| What                         | Where                                                   |
| ---------------------------- | ------------------------------------------------------- |
| Background gradient speed    | `--bg-cycle-duration` in `src/styles/theme.css`         |
| Background shimmer speed     | `--bg-shimmer-duration` in `src/styles/theme.css`       |
| Orbit sizes / speeds/planets | `ORBITS` in `src/components/background/OrbitalSystem.jsx` |
| Cursor trail density / fade  | `CURSOR_TRAIL` in `src/config/animation.js`             |
| Number of background stars   | `STAR_FIELD` in `src/config/animation.js`               |
| Player FPS / speeds          | `PLAYER` in `src/config/animation.js`                   |
| Fonts, sizes, letter-spacing | `src/styles/typography.css` (+ font link in `index.html`) |
| Colours                      | `src/styles/theme.css`                                  |

