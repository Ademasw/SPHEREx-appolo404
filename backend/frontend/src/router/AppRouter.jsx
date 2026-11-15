/**
 * src/router/AppRouter.jsx — all routes in one place.
 *
 *   /                    -> Page 1: LandingPage (immersive, cursor star-trail ON)
 *   /dashboard           -> redirects to /dashboard/advanced (Explore)
 *   /dashboard/player    -> Page 2: Dashboard, View Mode A (GIF / player)
 *   /dashboard/compare   -> Page 3: Dashboard, View Mode B (side-by-side epochs)
 *
 * Page transitions: <AnimatePresence> fades pages in/out. The <Routes> key is
 * the TOP-LEVEL segment ("" or "dashboard"), so switching between the two
 * dashboard modes does NOT remount the sidebar — only the inner view animates.
 */
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';

import LandingPage from '../pages/LandingPage/LandingPage.jsx';
import Dashboard from '../pages/Dashboard/Dashboard.jsx';
import PlayerView from '../pages/Dashboard/PlayerView.jsx';
import AdvancedView from '../pages/Dashboard/AdvancedView.jsx';
import CompareView from '../pages/Dashboard/CompareView.jsx';
import ColourView from '../pages/Dashboard/ColourView.jsx';
import PageTransition from '../components/layout/PageTransition.jsx';

export default function AppRouter() {
  const location = useLocation();
  const sectionKey = location.pathname.split('/')[1] || 'home';

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={sectionKey}>
        <Route
          path="/"
          element={
            <PageTransition>
              <LandingPage />
            </PageTransition>
          }
        />

        <Route
          path="/dashboard"
          element={
            <PageTransition>
              <Dashboard />
            </PageTransition>
          }
        >
          <Route index element={<Navigate to={{ pathname: "advanced", search: location.search }} replace />} />
          <Route path="advanced" element={<AdvancedView />} />
          <Route path="player" element={<PlayerView />} />
          <Route path="compare" element={<CompareView />} />
          <Route path="colour" element={<ColourView />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}
