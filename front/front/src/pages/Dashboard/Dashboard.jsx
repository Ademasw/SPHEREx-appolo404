/**
 * Dashboard — layout shared by Page 2 (Player) and Page 3 (Compare).
 *
 * - Minimalist: same animated gradient background (from App.jsx), but NO
 *   StarField, NO orbits and NO <CursorTrail/> — nothing distracts from data.
 * - Left: <Sidebar/> (logo, functional menu, coordinates input, view switcher).
 * - Right: active media view (<Outlet/>) + active functional panel
 *   (Overview metadata / Filter: Zodi Subtraction / Settings).
 */
import { useCallback, useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';

import Sidebar from './Sidebar.jsx';
import DashboardPanel from './DashboardPanel.jsx';
import {
  DEFAULT_FILTER,
  DEFAULT_SETTINGS,
  fetchObservation,
  getPlaceholderObservation,
  isBackendConfigured,
  subscribeObservationStream,
} from '../../services/observationApi';
import './Dashboard.css';

export default function Dashboard() {
  const location = useLocation();
  const [coordinates, setCoordinates] = useState('');
  const [activeMenu, setActiveMenu] = useState('overview');
  const [filterConfig, setFilterConfig] = useState(DEFAULT_FILTER);
  const [settingsConfig, setSettingsConfig] = useState(DEFAULT_SETTINGS);

  const [observation, setObservation] = useState(() =>
    getPlaceholderObservation({ coordinates: '', filter: DEFAULT_FILTER, settings: DEFAULT_SETTINGS }),
  );
  const [status, setStatus] = useState(isBackendConfigured() ? 'loading' : 'placeholder');
  const [error, setError] = useState(null);

  const loadObservation = useCallback(async (params, signal) => {
    setError(null);

    if (!isBackendConfigured()) {
      setObservation(getPlaceholderObservation(params));
      setStatus('placeholder');
      return;
    }

    setStatus('loading');
    try {
      const data = await fetchObservation(params, { signal });
      setObservation(data);
      setStatus('ready');
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message || 'Failed to load observation from backend.');
      setStatus('error');
    }
  }, []);

  // Re-fetch and re-subscribe whenever coordinates, Zodi filter, or settings change.
  useEffect(() => {
    const params = { coordinates, filter: filterConfig, settings: settingsConfig };
    const controller = new AbortController();
    loadObservation(params, controller.signal);

    const unsubscribe = subscribeObservationStream(params, {
      onData: (payload) => {
        setObservation(payload);
        setError(null);
      },
      onStatus: (nextStatus) => {
        if (nextStatus === 'live') setStatus('live');
        else if (nextStatus === 'error') setStatus('error');
      },
      onError: (err) => setError(err?.message || 'Stream error'),
    });

    return () => {
      controller.abort();
      unsubscribe();
    };
  }, [coordinates, filterConfig, settingsConfig, loadObservation]);

  return (
    <div className="dashboard">
      <Sidebar
        coordinates={coordinates}
        onCoordinatesSubmit={setCoordinates}
        activeMenu={activeMenu}
        onSelectMenu={setActiveMenu}
        zodiEnabled={filterConfig.enabled}
      />

      <main className="dashboard__main">
        {/* Keyed by path -> a quick fade whenever the view mode switches. */}
        <motion.div
          key={location.pathname}
          className="dashboard__view"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
        >
          <Outlet
            context={{
              coordinates,
              observation,
              status,
              error,
              zodiEnabled: filterConfig.enabled,
              onToggleZodi: () =>
                setFilterConfig((prev) => ({ ...prev, enabled: !prev.enabled })),
              activeMenu,
              onSelectMenu: setActiveMenu,
            }}
          />

          <DashboardPanel
            activeMenu={activeMenu}
            onClose={() => setActiveMenu(null)}
            observation={observation}
            filterConfig={filterConfig}
            onApplyFilter={setFilterConfig}
            settingsConfig={settingsConfig}
            onApplySettings={setSettingsConfig}
            onSelectCoordinates={setCoordinates}
          />
        </motion.div>
      </main>
    </div>
  );
}
