/**
 * OrbitalSystem — 3D tilted orbital plane viewed from slightly above, with
 * camera-facing (billboarded) 3D planets and subtle mouse parallax.
 *
 * HOW THE 3D EFFECT WORKS
 *   1. `.orbital-system` sets `perspective: 1100px`.
 *   2. `.orbital-system__plane` tilts the whole system with
 *      `rotateZ(var(--plane-roll)) rotateX(var(--plane-tilt))` so circular
 *      orbits become 3D ellipses viewed from above.
 *   3. Each `.orbit` spins in that 3D plane (`rotateZ(0 -> 360deg)`).
 *   4. Each `.orbit__planet-carrier` counter-rotates (`rotateZ(-θ) rotateX(-tilt)`)
 *      so the planet sprite stays upright facing the camera (never squashed
 *      flat) while moving closer/farther in true 3D Z-space, growing larger
 *      and brighter on the near side of its orbit.
 *
 * HOW TO CUSTOMISE (edit the ORBITS array below)
 *   size        orbit diameter (`vmin` keeps it responsive)
 *   duration    seconds per revolution -> LOWER = FASTER
 *   planet      image from ASSETS.planets (swap PNGs in src/assets/)
 *   planetSize  planet diameter in px
 *   startAngle  initial angle along the orbit (0-360°)
 *   reverse     true = counter-clockwise
 *   dashed      true = dashed orbit ring (e.g. candidate Planet X)
 *   hasRing     true = adds a tilted planetary ring around the planet
 */
import { useEffect, useRef } from 'react';
import { ASSETS } from '../../assets';
import './OrbitalSystem.css';

const ORBITS = [
  { size: '34vmin', duration: 12, planet: ASSETS.planets.planet3, planetSize: 22, startAngle: 25 },
  { size: '52vmin', duration: 20, planet: ASSETS.planets.planet2, planetSize: 34, startAngle: 195, reverse: true },
  {
    size: '74vmin',
    duration: 30,
    planet: ASSETS.planets.planet1,
    planetSize: 48,
    startAngle: 115,
    hasRing: true,
  },
  {
    size: '98vmin',
    duration: 44,
    planet: ASSETS.planets.planet4,
    planetSize: 30,
    startAngle: 285,
    reverse: true,
  },
  {
    size: '122vmin',
    duration: 62,
    planet: ASSETS.planets.planet1,
    planetSize: 26,
    startAngle: 60,
    dashed: true,
  },
];

export default function OrbitalSystem() {
  const sceneRef = useRef(null);

  // Subtle 3D camera parallax when moving the mouse on the landing page.
  useEffect(() => {
    const el = sceneRef.current;
    if (!el) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;

    const onMove = (e) => {
      const nx = (e.clientX / window.innerWidth - 0.5) * 2; // -1 .. 1
      const ny = (e.clientY / window.innerHeight - 0.5) * 2; // -1 .. 1
      el.style.setProperty('--parallax-x', `${(-ny * 4.5).toFixed(2)}deg`);
      el.style.setProperty('--parallax-y', `${(nx * 5.5).toFixed(2)}deg`);
    };

    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, []);

  return (
    <div ref={sceneRef} className="orbital-system" aria-hidden="true">
      <div className="orbital-system__plane">
        <div className="orbital-system__core" />
        <div className="orbital-system__core-halo" />

        {ORBITS.map((orbit, i) => {
          const delay = `-${((orbit.startAngle / 360) * orbit.duration).toFixed(2)}s`;
          const direction = orbit.reverse ? 'reverse' : 'normal';

          return (
            <div
              key={i}
              className={`orbit${orbit.dashed ? ' orbit--dashed' : ''}`}
              style={{
                '--orbit-size': orbit.size,
                animationDuration: `${orbit.duration}s`,
                animationDirection: direction,
                animationDelay: delay,
              }}
            >
              <div
                className="orbit__planet-carrier"
                style={{
                  '--planet-size': `${orbit.planetSize}px`,
                  animationDuration: `${orbit.duration}s`,
                  animationDirection: direction,
                  animationDelay: delay,
                }}
              >
                <div className={`orbit__planet-3d${orbit.hasRing ? ' orbit__planet-3d--ringed' : ''}`}>
                  <img src={orbit.planet} alt="" className="orbit__planet" />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
