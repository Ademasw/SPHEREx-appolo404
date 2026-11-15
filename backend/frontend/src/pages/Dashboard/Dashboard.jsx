/**
 * Dashboard — layout shared by Page 2 (Player) and Page 3 (Compare).
 *
 * - Minimalist: same animated gradient background (from App.jsx), but NO
 *   StarField, NO orbits and NO <CursorTrail/> — nothing distracts from data.
 * - Left: <Sidebar/> (logo, coordinates input, view switcher).
 * - Main: shared Overview and Settings accordions above the active media view.
 */
import { useCallback, useEffect, useMemo, useState, useRef } from 'react';
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
import { parseViewerQuery } from '../../services/viewerQuery.js';
import ScienceInspector from './ScienceInspector.jsx';

export default function Dashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const query = new URLSearchParams(location.search);
  const parsed = useMemo(() => {
    try { return { value: parseViewerQuery(location.search) }; }
    catch (error) { return { error: error.message }; }
  }, [location.search]);
  const coordinates = query.get('q') || (query.has('ra') && query.has('dec') ? query.get('ra') + ' ' + query.get('dec') : location.state?.coordinates || '');
  const setCoordinates = value => {
    const next = new URLSearchParams(location.search);
    next.set('q', value); next.delete('ra'); next.delete('dec');
    navigate({ pathname: location.pathname, search: '?' + next }, { replace: true });
  };
  const filterConfig = useMemo(() => ({ ...DEFAULT_FILTER, enabled: parsed.value?.bg !== 'none', background: parsed.value?.bg || 'model' }), [parsed]);
  const setFilter = value => {
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
      playerFps: parsed.value?.playerFps ?? 3,
      epoch1Label: parsed.value?.epoch1Label || 'Epoch 1',
      epoch2Label: parsed.value?.epoch2Label || 'Epoch 2',
      ...(params.has('displayDet') ? { displayDetector: parsed.value?.displayDetector } : {}),
    };
  }, [localSettings, location.search, parsed]);
  const setSettingsConfig = value => {
    setLocalSettings(value);
    const next = new URLSearchParams(location.search);
    next.set('det', value.detectorArray === 'all' ? 'all' : 'D' + value.detectorArray);
    next.set('fov', String(Number(value.fovArcmin) / 60));
    next.set('epoch1', value.epoch1Date || '');
    next.set('epoch2', value.epoch2Date || '');
    next.set('clean', value.cleanMask ? 'true' : 'false');
    next.set('smooth', value.smoothDisplay === false ? 'false' : 'true');
    next.set('fps', String(value.playerFps));
    next.set('label1', value.epoch1Label || 'Epoch 1');
    next.set('label2', value.epoch2Label || 'Epoch 2');
    if (value.displayDetector) next.set('displayDet', value.displayDetector);
    navigate({ pathname: location.pathname, search: '?' + next }, { replace: true });
  };

  const [observation, setObservation] = useState(() =>
    getPlaceholderObservation({ coordinates: '', filter: DEFAULT_FILTER, settings: DEFAULT_SETTINGS }),
  );
  const [status, setStatus] = useState(isBackendConfigured() ? 'loading' : 'placeholder');
  const [error, setError] = useState(null);
  const [reload, setReload] = useState(0);
  const refreshNext = useRef(false);
  const waiting = useRef(null);

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
      const refresh = refreshNext.current;
      refreshNext.current = false;
      const data = await fetchObservation(params, { signal, refresh });
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
    if (parsed.error) {
      setError(parsed.error); setStatus('error');
      setObservation(getPlaceholderObservation());
      return;
    }
    const params = { coordinates, filter: filterConfig, settings: settingsConfig };
    const controller = new AbortController();
    waiting.current = controller;
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
  }, [coordinates, filterConfig, settingsConfig, loadObservation, parsed, reload]);

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
          {!location.pathname.endsWith('/advanced') && coordinates && <p>
            <button disabled={status === 'loading'} onClick={() => {refreshNext.current = true; setReload(value => value + 1);}}>Refresh archive</button>
            {status === 'loading' && <button onClick={() => {waiting.current?.abort(); setStatus('idle');}}>Stop waiting</button>}
            {status === 'loading' && <span> Server processing continues safely if you stop waiting.</span>}
          </p>}
          <ScienceInspector observation={observation} status={status} />

        </motion.div>
      </main>
    </div>
  );
}
