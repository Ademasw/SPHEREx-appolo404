/**
 * CursorTrail — drop-in component that enables the PNG star trail.
 *
 * USAGE
 *   Render <CursorTrail /> inside any page that should have the effect.
 *   It is mounted ONLY in LandingPage, which is how the trail is disabled on
 *   the Dashboard pages: when the landing page unmounts, the hook removes its
 *   listener and clears all particles.
 *
 * PROPS
 *   sources  PNG URLs to use (default: ASSETS.trailParticles -> src/assets/star-particle*.png)
 *   options  overrides for CURSOR_TRAIL (src/config/animation.js), e.g. { maxSize: 40 }
 */
import { useRef } from 'react';
import useCursorTrail from '../../hooks/useCursorTrail';
import { ASSETS } from '../../assets';
import './CursorTrail.css';

export default function CursorTrail({ sources = ASSETS.trailParticles, options }) {
  const layerRef = useRef(null);
  useCursorTrail(layerRef, sources, options);

  return <div ref={layerRef} className="cursor-trail" aria-hidden="true" />;
}

