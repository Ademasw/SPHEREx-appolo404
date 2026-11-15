/**
 * AnimatedBackground — the global shimmering Deep Black <-> Deep Purple gradient.
 *
 * Pure CSS (no JS per frame) for performance:
 *   - Layer 1 (`.animated-bg`): an oversized linear gradient whose
 *     background-position pans back and forth -> smooth colour transition.
 *   - Layer 2 (`::before` / `::after`): soft radial "light blobs" that drift and
 *     pulse in opacity -> the shimmer.
 *
 * SPEED: edit `--bg-cycle-duration` and `--bg-shimmer-duration` in
 *        src/styles/theme.css. COLOURS: the --color-* variables in the same file.
 */
import './AnimatedBackground.css';

export default function AnimatedBackground() {
  return <div className="animated-bg" aria-hidden="true" />;
}

