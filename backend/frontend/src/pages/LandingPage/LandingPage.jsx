/**
 * LandingPage — Page 1 (extended downwards: Hero + Infrared Sky Map
 * right beneath the introductory words and CTA button).
 *
 * Layer stack (bottom -> top):
 *   0. <AnimatedBackground/>  global gradient (rendered in App.jsx)
 *   1. <StarField/>           background stars across the extended landing page
 *   2. <OrbitalSystem/>       3D tilted planetary orbits
 *   3. <Header/>              top navigation bar
 *   4. <main.landing__hero>   introductory words + "Let's Go!" CTA +
 *                             Aladin-Lite style Infrared Sky Map
 *   5. <CursorTrail/>         PNG star particles following the mouse
 */
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';

import Header from '../../components/layout/Header.jsx';
import StarField from '../../components/background/StarField.jsx';
import OrbitalSystem from '../../components/background/OrbitalSystem.jsx';
import CursorTrail from '../../components/cursor/CursorTrail.jsx';
import CelestialGlobe from '../../components/globe/CelestialGlobe.jsx';
import { PROJECT } from '../../config/project';
import { ROUTES } from '../../router/routes';
import './LandingPage.css';

/** Staggered fade-up for hero elements. Increase `duration` for a slower reveal. */
const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.8, delay, ease: [0.22, 1, 0.36, 1] },
});

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="landing">
      <StarField count={200} />
      <OrbitalSystem />
      <Header />

      <main className="landing__hero">
        <div className="landing__intro">
          <motion.p className="landing__eyebrow text-label text-accent" {...fadeUp(0.1)}>
            {PROJECT.challenge} · Planet X &amp; SPHEREx
          </motion.p>

          <motion.h1 className="landing__title text-display text-gradient" {...fadeUp(0.25)}>
            {/* HERO TITLE placeholder */}
            Hunting for
            <br />
            Planet X
          </motion.h1>

          <motion.p className="landing__thanks text-body-lg text-muted" {...fadeUp(0.45)}>
            {/* THANK-YOU TEXT placeholder */}
            Thank you, NASA and the SPHEREx mission team, for opening the infrared sky to everyone. This project is our
            attempt to turn your all-sky data into a search for the unseen.
          </motion.p>

          <motion.button
            type="button"
            className="landing__cta text-button"
            onClick={() => navigate({ pathname: ROUTES.compare, search: '?q=Barnard%27s%20Star&det=D6&fov=0.1' })}
            {...fadeUp(0.6)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.97 }}
          >
            Let&apos;s Go!
            <span className="landing__cta-arrow" aria-hidden="true">
              →
            </span>
          </motion.button>
        </div>

        {/* ---- ALADIN-STYLE 3D CELESTIAL PHOTO GLOBE DIRECTLY BELOW INTRO ---- */}
        <motion.section
          id="sky-globe"
          className="landing__globe-block"
          aria-label="Infrared Sky Map"
          {...fadeUp(0.75)}
        >
          <div className="landing__globe-header">
            <p className="text-label text-accent">NASA / IPAC IRSA · AllWISE</p>
            <h2 className="text-h1">Infrared Sky Map</h2>
            <p className="text-body text-muted landing__globe-subtitle">
              Explore the infrared sky. Drag to move · scroll or pinch to zoom.
            </p>
          </div>

          <CelestialGlobe />
        </motion.section>
      </main>

      <CursorTrail />
    </div>
  );
}
