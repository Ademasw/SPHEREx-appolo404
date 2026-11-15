/**
 * src/config/animation.js — JS-driven animation knobs in one place.
 * -------------------------------------------------------------------------
 * Pure-CSS animation speeds live in CSS variables instead:
 *   - Background gradient speed  -> `--bg-cycle-duration` (src/styles/theme.css)
 *   - Background shimmer speed   -> `--bg-shimmer-duration` (src/styles/theme.css)
 *   - Orbit speeds               -> `ORBITS` array (src/components/background/OrbitalSystem.jsx)
 * -------------------------------------------------------------------------
 */

/** Cursor star-trail (Landing page only). */
export const CURSOR_TRAIL = {
  /** Minimum ms between spawns. Lower = denser trail (and more CPU). */
  spawnIntervalMs: 28,
  /** Mouse must move at least this many px before a new spawn. */
  minDistancePx: 10,
  /** Particles created per spawn event. */
  particlesPerSpawn: 1,
  /** Particle size range in px (random in between). */
  minSize: 8,
  maxSize: 26,
  /** Fade-out duration range in ms. Higher = longer, lazier trail. */
  minLifetimeMs: 650,
  maxLifetimeMs: 1300,
  /** Max px a particle drifts away from where it spawned. */
  driftPx: 40,
  /** Random offset from the exact cursor point, in px. */
  jitterPx: 8,
  /** Hard cap on simultaneous particles (protects low-end devices). */
  maxParticles: 80,
};

/** Static background stars (Landing page). */
export const STAR_FIELD = {
  count: 140,
  minSize: 2,
  maxSize: 12,
};

/** Dashboard player (View Mode A). */
export const PLAYER = {
  /** Base playback speed for image sequences (frames per second at 1×). */
  framesPerSecond: 3,
  /** Speed multipliers offered in the UI. */
  speeds: [0.5, 1, 2],
  autoplay: true,
};

