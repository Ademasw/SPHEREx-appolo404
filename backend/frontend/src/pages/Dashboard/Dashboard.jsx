/**
 * Dashboard — layout shared by Page 2 (Player) and Page 3 (Compare).
 *
 * - Minimalist: same animated gradient background (from App.jsx), but NO
 *   StarField, NO orbits and NO <CursorTrail/> — nothing distracts from data.
 * - Left: <Sidebar/> (logo, coordinates input, view switcher).
 * - Main: shared Overview and Settings accordions above the active media view.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
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
  const navigate = useNavigate();
  const query = new URLSearchParams(location.search);
  const coordinates = query.get('q') || (query.has('ra') && query.has('dec') ? query.get('ra') + ' ' + query.get('dec') : location.state?.coordinates || '');
  const setCoordinates = value => {
    const next = new URLSearchParams(location.search);
    next.set('q', value); next.delete('ra'); next.delete('dec');
    navigate({ pathname: location.pathname, search: '?' + next }, { replace: true });
  };
  const [filterConfig, setFilterConfig] = useState(() => ({ ...DEFAULT_FILTER, enabled: query.get('bg') !== 'none' }));
  const setFilter = value => {
    setFilterConfig(value);
    const next = new URLSearchParams(location.search);
    next.set('bg', value.enabled ? 'model' : 'none');
    navigate({ pathname: location.pathname, search: '?' + next }, { replace: true });
  };
  const [localSettings, setLocalSettings] = useState(DEFAULT_SETTINGS);
  const settingsConfig = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return {
      ...localSettings,
      epoch1Date: params.get('epoch1') || '',
      epoch2Date: params.get('epoch2') || '',
      detectorArray: /^D[1-6]$/.test(params.get('det')) ? params.get('det').slice(1) : params.get('det') === 'all' ? 'all' : DEFAULT_SETTINGS.detectorArray,
      fovArcmin: [0.05, 0.1, 0.2].includes(Number(params.get('fov'))) ? String(Number(params.get('fov')) * 60) : DEFAULT_SETTINGS.fovArcmin,
      cleanMask: params.get('clean') === 'true',
      smoothDisplay: params.get('smooth') !== 'false',
    };
  }, [localSettings, location.search]);
  const setSettingsConfig = value => {
    setLocalSettings(value);
    const next = new URLSearchParams(location.search);
    next.set('det', value.detectorArray === 'all' ? 'all' : 'D' + value.detectorArray);
    next.set('fov', String(Number(value.fovArcmin) / 60));
    next.set('epoch1', value.epoch1Date || '');
    next.set('epoch2', value.epoch2Date || '');
    next.set('clean', value.cleanMask ? 'true' : 'false');
    next.set('smooth', value.smoothDisplay === false ? 'false' : 'true');
    navigate({ pathname: location.pathname, search: '?' + next }, { replace: true });
  };

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
    setObservation(getPlaceholderObservation(params));
    try {
      const data = await fetchObservation(params, { signal });
      if (signal.aborted) return;
      setObservation(data);
      setStatus(params.coordinates.trim() ? 'ready' : 'idle');
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
      <Sidebar coordinates={coordinates} onCoordinatesSubmit={setCoordinates} />

      <main className="dashboard__main">
        {/* Keyed by path -> a quick fade whenever the view mode switches. */}
        <motion.div
          key={location.pathname}
          className="dashboard__view"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
        >
          <DashboardPanel
            observation={observation}
            filterConfig={filterConfig}
            onApplyFilter={setFilter}
            settingsConfig={settingsConfig}
            onApplySettings={setSettingsConfig}
            onSelectCoordinates={setCoordinates}
          />

          <Outlet
            context={{
              coordinates,
              observation,
              status,
              error,
            }}
          />

        </motion.div>
      </main>
    </div>
  );
}
