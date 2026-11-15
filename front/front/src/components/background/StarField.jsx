/**
 * StarField — randomly scattered STATIC stars (PNG sprites).
 *
 * - Sprites come from `ASSETS.stars` (src/assets/star1.png, star2.png ...).
 *   Add more PNGs to that array for more variety.
 * - Positions are generated ONCE per mount (useMemo), so stars don't jump
 *   around on re-render.
 * - Count / size range: `STAR_FIELD` in src/config/animation.js
 *   (or pass `count` as a prop).
 */
import { useMemo } from 'react';
import { ASSETS } from '../../assets';
import { STAR_FIELD } from '../../config/animation';
import './StarField.css';

const random = (min, max) => min + Math.random() * (max - min);

export default function StarField({ count = STAR_FIELD.count }) {
  const stars = useMemo(
    () =>
      Array.from({ length: count }, (_, id) => {
        // Bias toward small stars: most are tiny, a few are big.
        const size = STAR_FIELD.minSize + Math.random() ** 3 * (STAR_FIELD.maxSize - STAR_FIELD.minSize);
        return {
          id,
          src: ASSETS.stars[Math.floor(Math.random() * ASSETS.stars.length)],
          left: random(0, 100),
          top: random(0, 100),
          size,
          opacity: random(0.35, 1),
          twinkle: Math.random() > 0.55,
          duration: random(2.6, 6.2).toFixed(2),
          delay: random(0, 5).toFixed(2),
        };
      }),
    [count],
  );

  return (
    <div className="star-field" aria-hidden="true">
      {stars.map((s) => (
        <img
          key={s.id}
          src={s.src}
          alt=""
          className={`star-field__star${s.twinkle ? ' star-field__star--twinkle' : ''}`}
          style={{
            left: `${s.left}%`,
            top: `${s.top}%`,
            width: `${s.size}px`,
            height: `${s.size}px`,
            '--star-opacity': s.opacity,
            animationDuration: s.twinkle ? `${s.duration}s` : undefined,
            animationDelay: s.twinkle ? `-${s.delay}s` : undefined,
          }}
        />
      ))}
    </div>
  );
}

