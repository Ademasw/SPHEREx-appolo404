/**
 * src/assets/index.js — THE SINGLE PLACE WHERE IMAGES ARE IMPORTED
 * -------------------------------------------------------------------------
 * HOW TO SWAP ASSETS
 *   Option A (easiest): drop your own PNG into `src/assets/` with the SAME
 *            file name (e.g. overwrite `planet1.png`). Nothing else changes.
 *   Option B: add a new file (e.g. `saturn.png`), import it below, and put it
 *            in the right group of the `ASSETS` object.
 *
 * Components never import images directly — they read from `ASSETS`, so
 * renaming / re-organising images only ever touches this file.
 *
 * Tip: transparent PNGs work best for stars, particles and planets.
 * -------------------------------------------------------------------------
 */

// --- Branding --------------------------------------------------------------
import logo from './logo.png'; // Team / project logo (square, transparent PNG)

// --- Cursor-trail particles (Landing page only) ------------------------------
// Add as many as you like; one is picked at random for every spawned particle.
import starParticle1 from './star-particle.png';
import starParticle2 from './star-particle-2.png';
import starParticle3 from './star-particle-3.png';

// --- Static background stars ------------------------------------------------
import star1 from './star1.png';
import star2 from './star2.png';

// --- Orbiting planets (Landing page) ----------------------------------------
import planet1 from './planet1.png';
import planet2 from './planet2.png';
import planet3 from './planet3.png';
import planet4 from './planet4.png';

// --- Dashboard: image sequence for the player (View Mode A) -----------------
// Replace with your own frames (any count). For a real video, see
// `src/pages/Dashboard/PlayerView.jsx` (pass `videoSrc` instead of frames).
import frame01 from './frame-01.png';
import frame02 from './frame-02.png';
import frame03 from './frame-03.png';
import frame04 from './frame-04.png';
import frame05 from './frame-05.png';
import frame06 from './frame-06.png';

// --- Dashboard: two epochs for side-by-side comparison (View Mode B) --------
import epochA from './epoch-a.png';
import epochB from './epoch-b.png';

export const ASSETS = {
  logo,
  trailParticles: [starParticle1, starParticle2, starParticle3],
  stars: [star1, star2],
  planets: { planet1, planet2, planet3, planet4 },
  playerFrames: [frame01, frame02, frame03, frame04, frame05, frame06],
  epochs: { a: epochA, b: epochB },
};

export default ASSETS;

