/**
 * useCursorTrail — spawns PNG star particles that trail behind the mouse.
 * -------------------------------------------------------------------------
 * WHY DIRECT DOM INSTEAD OF REACT STATE?
 *   Mouse events fire ~60-120×/s. Storing particles in React state would
 *   re-render on every move. Instead we append lightweight <img> nodes to a
 *   layer element and let a CSS animation fade them out; each node removes
 *   itself on `animationend`. React never re-renders.
 *
 * HOW A PARTICLE IS BUILT
 *   - `src`   : random pick from `sources` (PNG files in src/assets/)
 *   - size    : random between minSize/maxSize
 *   - --dx/--dy: random drift direction, --rot: random spin
 *   - --life  : random lifetime -> drives the CSS fade (see CursorTrail.css)
 *
 * TUNING: defaults come from `CURSOR_TRAIL` in src/config/animation.js;
 *         any of them can be overridden via the `options` argument.
 *
 * AUTO-DISABLED on touch-only devices and when the OS requests reduced motion.
 * -------------------------------------------------------------------------
 *
 * @param {React.RefObject<HTMLElement>} layerRef  element that receives particles
 * @param {string[]} sources                      PNG URLs (imported from src/assets)
 * @param {Partial<typeof CURSOR_TRAIL>} [options]
 */
import { useEffect, useRef } from 'react';
import { CURSOR_TRAIL } from '../config/animation';

const rand = (min, max) => min + Math.random() * (max - min);

export default function useCursorTrail(layerRef, sources, options = {}) {
  // Keep latest options in a ref so changing them doesn't re-attach listeners.
  const optsRef = useRef({ ...CURSOR_TRAIL, ...options });
  optsRef.current = { ...CURSOR_TRAIL, ...options };

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer || !sources?.length) return undefined;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const noFinePointer = !window.matchMedia('(any-pointer: fine)').matches;
    if (reducedMotion || noFinePointer) return undefined;

    // Preload sprites so the first particles don't flash in.
    sources.forEach((src) => {
      const img = new Image();
      img.src = src;
    });

    let lastX = -9999;
    let lastY = -9999;
    let lastTime = 0;

    const spawn = (x, y) => {
      const o = optsRef.current;

      // Enforce the particle cap: drop the oldest one.
      if (layer.childElementCount >= o.maxParticles) layer.firstElementChild?.remove();

      const img = document.createElement('img');
      img.src = sources[Math.floor(Math.random() * sources.length)];
      img.alt = '';
      img.draggable = false;
      img.className = 'cursor-trail__particle';

      const size = rand(o.minSize, o.maxSize);
      const angle = rand(0, Math.PI * 2);
      const drift = rand(o.driftPx * 0.3, o.driftPx);

      img.style.setProperty('--x', `${x + rand(-o.jitterPx, o.jitterPx)}px`);
      img.style.setProperty('--y', `${y + rand(-o.jitterPx, o.jitterPx)}px`);
      img.style.setProperty('--size', `${size}px`);
      img.style.setProperty('--dx', `${Math.cos(angle) * drift}px`);
      // Slight downward bias makes the trail feel like falling stardust.
      img.style.setProperty('--dy', `${Math.sin(angle) * drift + drift * 0.4}px`);
      img.style.setProperty('--rot', `${rand(-180, 180)}deg`);
      img.style.setProperty('--life', `${rand(o.minLifetimeMs, o.maxLifetimeMs)}ms`);

      img.addEventListener('animationend', () => img.remove(), { once: true });
      layer.appendChild(img);
    };

    const onPointerMove = (e) => {
      if (e.pointerType && e.pointerType !== 'mouse' && e.pointerType !== 'pen') return;
      const o = optsRef.current;
      const now = performance.now();
      const dist = Math.hypot(e.clientX - lastX, e.clientY - lastY);

      // Throttle by BOTH time and distance -> even density at any mouse speed.
      if (now - lastTime < o.spawnIntervalMs || dist < o.minDistancePx) return;
      lastTime = now;
      lastX = e.clientX;
      lastY = e.clientY;

      for (let i = 0; i < o.particlesPerSpawn; i++) spawn(e.clientX, e.clientY);
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });

    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      layer.replaceChildren(); // clean up any particles still on screen
    };
  }, [layerRef, sources]);
}

