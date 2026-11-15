/**
 * src/services/observationApi.js — BACKEND INTEGRATION LAYER FOR MEDIA WINDOWS
 * -------------------------------------------------------------------------
 * Both Dashboard media windows (PlayerView + CompareView) and the Overview
 * metadata panel read from one normalized `ObservationPayload` object.
 *
 * HOW TO CONNECT YOUR BACKEND LATER
 *   1. Set `VITE_API_BASE_URL=http://localhost:8000` in `front/.env.local`.
 *   2. Optionally set `VITE_STREAM_MODE=sse` (or `ws`) for live backend pushes.
 *   3. Accept query parameters on:
 *        GET {VITE_API_BASE_URL}/api/observations
 *          ?coords=<RA,Dec>
 *          &zodi=<0|1>
 *          &zodi_model=<kelsall|spherex|median>
 *          &zodi_strength=<0..150>
 *          &epoch1=<YYYY-MM-DD>
 *          &epoch2=<YYYY-MM-DD>
 *          &fov=<arcmin>
 *          &array=<all|1..6>
 *
 * When `VITE_API_BASE_URL` is empty, the app uses local placeholder assets
 * from `src/assets/` and reflects the active filter/settings in metadata.
 * -------------------------------------------------------------------------
 */
import { ASSETS } from '../assets';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const STREAM_MODE = (import.meta.env.VITE_STREAM_MODE || 'none').toLowerCase();

export const isBackendConfigured = () => Boolean(API_BASE);

export const DEFAULT_FILTER = {
  enabled: true,
  model: 'kelsall', // 'kelsall' | 'spherex' | 'median'
  strength: 100, // 0..150 (%)
  maskSaturated: false,
};

export const DEFAULT_SETTINGS = {
  epoch1Label: 'Epoch 1',
  epoch1Date: '2025-05-01',
  epoch2Label: 'Epoch 2',
  epoch2Date: '2025-11-01',
  fovArcmin: '10',
  detectorArray: 'all',
  playerFps: 3,
};

function buildQueryParams({ coordinates = '', filter = DEFAULT_FILTER, settings = DEFAULT_SETTINGS } = {}) {
  const params = new URLSearchParams();
  if (coordinates) params.set('coords', coordinates);
  params.set('zodi', filter.enabled ? '1' : '0');
  params.set('zodi_model', filter.model);
  params.set('zodi_strength', String(filter.strength));
  if (filter.maskSaturated) params.set('mask_saturated', '1');
  if (settings.epoch1Date) params.set('epoch1', settings.epoch1Date);
  if (settings.epoch2Date) params.set('epoch2', settings.epoch2Date);
  if (settings.fovArcmin) params.set('fov', String(settings.fovArcmin));
  if (settings.detectorArray) params.set('array', settings.detectorArray);
  const str = params.toString();
  return str ? `?${str}` : '';
}

/**
 * Default local placeholder payload (used before backend is connected).
 */
export function getPlaceholderObservation({
  coordinates = '',
  filter = DEFAULT_FILTER,
  settings = DEFAULT_SETTINGS,
} = {}) {
  const arrayLabel =
    settings.detectorArray === 'all' ? 'All 6 Arrays (0.75–5.0 μm)' : `Array ${settings.detectorArray}`;

  return {
    coordinates,
    source: 'placeholder',
    updatedAt: null,
    player: {
      mode: 'frames', // 'frames' | 'video' | 'stream'
      frames: ASSETS.playerFrames,
      videoUrl: null,
      streamUrl: null,
      fps: Number(settings.playerFps) || 3,
    },
    compare: {
      epochs: [
        {
          id: 'a',
          label: settings.epoch1Label || 'Epoch 1',
          date: settings.epoch1Date || '2025-05-01',
          imageUrl: ASSETS.epochs.a,
          meta: `${arrayLabel} · FOV ${settings.fovArcmin || 10}'`,
        },
        {
          id: 'b',
          label: settings.epoch2Label || 'Epoch 2',
          date: settings.epoch2Date || '2025-11-01',
          imageUrl: ASSETS.epochs.b,
          meta: `${arrayLabel} · FOV ${settings.fovArcmin || 10}'`,
        },
      ],
    },
    // Detailed metadata displayed in the Overview menu panel (not on main media area).
    metadata: {
      'Target Coordinates': coordinates || 'Not specified (placeholder field)',
      Instrument: 'SPHEREx All-Sky NIR Spectrograph',
      'Detector Array': arrayLabel,
      'Field of View': `${settings.fovArcmin || 10} × ${settings.fovArcmin || 10} arcmin`,
      Resolution: '512 × 384 px (cutout)',
      'Pixel Scale': '6.2 arcsec / px',
      'Zodi Subtraction': filter.enabled
        ? `ON (${filter.model.toUpperCase()} · ${filter.strength}%)`
        : 'OFF (raw sky background)',
      'Saturated Star Mask': filter.maskSaturated ? 'Enabled' : 'Disabled',
      'Frame Count': `${ASSETS.playerFrames.length} frames`,
      'Contamination Flag': 'Nominal (placeholder)',
      'Coordinate Frame': 'ICRS (J2000)',
    },
  };
}

/**
 * Normalizes any backend JSON payload (supports snake_case or camelCase fields)
 * into the canonical structure consumed by PlayerView, CompareView & Overview.
 */
export function normalizeObservationPayload(raw = {}, context = {}) {
  const base = getPlaceholderObservation(context);

  const playerRaw = raw.player || {};
  const frames = playerRaw.frames ?? raw.frames ?? base.player.frames;
  const videoUrl = playerRaw.videoUrl ?? playerRaw.video_url ?? raw.videoUrl ?? raw.video_url ?? null;
  const streamUrl =
    playerRaw.streamUrl ??
    playerRaw.stream_url ??
    playerRaw.gifUrl ??
    playerRaw.gif_url ??
    raw.streamUrl ??
    raw.gifUrl ??
    null;

  let mode = playerRaw.mode;
  if (!mode) {
    if (videoUrl) mode = 'video';
    else if (streamUrl) mode = 'stream';
    else mode = 'frames';
  }

  const epochsRaw = raw.compare?.epochs ?? raw.epochs;
  const epochs =
    Array.isArray(epochsRaw) && epochsRaw.length > 0
      ? epochsRaw.slice(0, 2).map((ep, idx) => ({
          id: ep.id ?? String(idx),
          label: ep.label ?? base.compare.epochs[idx]?.label ?? `Epoch ${idx + 1}`,
          date: ep.date ?? ep.timestamp ?? base.compare.epochs[idx]?.date ?? '—',
          imageUrl: ep.imageUrl ?? ep.image_url ?? ep.url ?? ep.src ?? '',
          meta: ep.meta ?? ep.band ?? base.compare.epochs[idx]?.meta ?? null,
        }))
      : base.compare.epochs;

  const extraMeta = raw.metadata || raw.telemetry || {};

  return {
    coordinates: raw.coordinates ?? context.coordinates ?? '',
    source: 'backend',
    updatedAt: raw.updatedAt ?? raw.updated_at ?? new Date().toISOString(),
    player: {
      mode,
      frames,
      videoUrl,
      streamUrl,
      fps: playerRaw.fps ?? base.player.fps,
    },
    compare: {
      epochs,
    },
    metadata: {
      ...base.metadata,
      ...extraMeta,
    },
  };
}

/**
 * Fetches observation data for the given sky coordinates, filter, and settings.
 */
export async function fetchObservation(params, { signal } = {}) {
  if (!API_BASE) {
    return getPlaceholderObservation(params);
  }

  const query = buildQueryParams(params);
  const response = await fetch(`${API_BASE}/api/observations${query}`, {
    signal,
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Backend responded with ${response.status} ${response.statusText}`);
  }

  const json = await response.json();
  return normalizeObservationPayload(json, params);
}

/**
 * Subscribes to real-time backend updates (SSE or WebSocket) when enabled via
 * `VITE_STREAM_MODE`. Returns an unsubscribe/cleanup function.
 */
export function subscribeObservationStream(params, { onData, onStatus, onError }) {
  if (!API_BASE || STREAM_MODE === 'none') {
    return () => {};
  }

  const query = buildQueryParams(params);

  if (STREAM_MODE === 'sse') {
    const source = new EventSource(`${API_BASE}/api/observations/stream${query}`);
    onStatus?.('connecting');

    source.onopen = () => onStatus?.('live');
    source.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        onData?.(normalizeObservationPayload(parsed, params));
        onStatus?.('live');
      } catch (err) {
        onError?.(err);
      }
    };
    source.onerror = () => onStatus?.('error');

    return () => source.close();
  }

  if (STREAM_MODE === 'ws') {
    const wsBase = API_BASE.replace(/^http/i, 'ws');
    const socket = new WebSocket(`${wsBase}/ws/observations${query}`);
    onStatus?.('connecting');

    socket.onopen = () => onStatus?.('live');
    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        onData?.(normalizeObservationPayload(parsed, params));
        onStatus?.('live');
      } catch (err) {
        onError?.(err);
      }
    };
    socket.onerror = () => {
      onStatus?.('error');
      onError?.(new Error('WebSocket connection error'));
    };

    return () => socket.close();
  }

  return () => {};
}

/* =========================================================================
   3D CELESTIAL GLOBE (ALADIN-STYLE SKY MAP ON LANDING PAGE)
   -------------------------------------------------------------------------
   The backend computes where each space photograph belongs on the celestial
   sphere (`ra`, `dec`) based on the Earth location (`lat`, `lon`) and time
   (`capturedAt`) where the photo was taken.

   Endpoint when backend is merged:
     GET {VITE_API_BASE_URL}/api/globe/tiles
   Expected JSON array item shape:
     {
       id: string,
       title: string,
       imageUrl: string,        // space photo wrapped onto the sphere
       ra: number,              // Right Ascension in degrees (0..360)
       dec: number,             // Declination in degrees (-90..+90)
       angularSize: number,     // tile footprint on sphere in degrees
       earthLat: number,        // Earth latitude where photo was captured
       earthLon: number,        // Earth longitude where photo was captured
       earthSite: string,       // Ground station / observatory name
       capturedAt: string,      // ISO timestamp
       band: string             // Spectral band
     }
   ========================================================================= */

const TILE_IMAGES = [
  ...ASSETS.playerFrames,
  ASSETS.epochs.a,
  ASSETS.epochs.b,
];

export const DEFAULT_GLOBE_TILES = [
  {
    id: 'tile-01',
    title: "Barnard's Star Sector",
    imageUrl: TILE_IMAGES[0],
    ra: 269.45,
    dec: 4.69,
    angularSize: 42,
    earthLat: 19.8207,
    earthLon: -155.4681,
    earthSite: 'Mauna Kea, Hawaii',
    capturedAt: '2025-05-12T09:15:00Z',
    band: 'NIR 0.75–5.0 μm',
  },
  {
    id: 'tile-02',
    title: 'WISE 0855 Brown Dwarf Field',
    imageUrl: TILE_IMAGES[1],
    ra: 133.79,
    dec: -7.24,
    angularSize: 42,
    earthLat: -24.6272,
    earthLon: -70.4042,
    earthSite: 'Paranal, Atacama',
    capturedAt: '2025-05-14T03:40:00Z',
    band: 'NIR 1.64–2.42 μm',
  },
  {
    id: 'tile-03',
    title: 'Epsilon Indi B Binary Region',
    imageUrl: TILE_IMAGES[2],
    ra: 330.84,
    dec: -46.78,
    angularSize: 42,
    earthLat: -31.2755,
    earthLon: 149.067,
    earthSite: 'Siding Spring, Australia',
    capturedAt: '2025-06-02T14:22:00Z',
    band: 'NIR 2.42–3.13 μm',
  },
  {
    id: 'tile-04',
    title: 'RW Aurigae Variable Field',
    imageUrl: TILE_IMAGES[3],
    ra: 76.96,
    dec: 30.4,
    angularSize: 42,
    earthLat: 28.7566,
    earthLon: -17.892,
    earthSite: 'Roque de los Muchachos, La Palma',
    capturedAt: '2025-07-19T23:10:00Z',
    band: 'NIR 0.75–1.11 μm',
  },
  {
    id: 'tile-05',
    title: 'R Draconis High-Dec Sector',
    imageUrl: TILE_IMAGES[4],
    ra: 248.16,
    dec: 56.75,
    angularSize: 42,
    earthLat: 43.255,
    earthLon: 76.95,
    earthSite: 'Tien Shan Observatory, Almaty',
    capturedAt: '2025-08-04T18:05:00Z',
    band: 'NIR 3.13–3.83 μm',
  },
  {
    id: 'tile-06',
    title: 'Ecliptic Plane Survey Patch A',
    imageUrl: TILE_IMAGES[5],
    ra: 18.5,
    dec: 12.0,
    angularSize: 42,
    earthLat: 31.9583,
    earthLon: -111.5967,
    earthSite: 'Kitt Peak, Arizona',
    capturedAt: '2025-09-01T06:50:00Z',
    band: 'NIR 3.83–5.00 μm',
  },
  {
    id: 'tile-07',
    title: 'Orion Molecular Cloud Cutout',
    imageUrl: TILE_IMAGES[6],
    ra: 83.82,
    dec: -5.39,
    angularSize: 42,
    earthLat: -30.169,
    earthLon: -70.806,
    earthSite: 'Cerro Tololo, Chile',
    capturedAt: '2025-09-18T05:12:00Z',
    band: 'NIR 0.75–5.0 μm',
  },
  {
    id: 'tile-08',
    title: 'Cygnus Rift Infrared Mosaic',
    imageUrl: TILE_IMAGES[7],
    ra: 305.0,
    dec: 38.0,
    angularSize: 42,
    earthLat: 33.3563,
    earthLon: -116.865,
    earthSite: 'Palomar Mountain, CA',
    capturedAt: '2025-10-03T04:30:00Z',
    band: 'NIR 1.11–1.64 μm',
  },
  {
    id: 'tile-09',
    title: 'Carina Deep Infrared Sector',
    imageUrl: TILE_IMAGES[0],
    ra: 161.2,
    dec: -49.8,
    angularSize: 42,
    earthLat: -32.379,
    earthLon: 20.81,
    earthSite: 'Sutherland, South Africa',
    capturedAt: '2025-10-15T21:40:00Z',
    band: 'NIR 2.42–3.13 μm',
  },
  {
    id: 'tile-10',
    title: ' Kuiper Belt Candidate Zone',
    imageUrl: TILE_IMAGES[2],
    ra: 215.0,
    dec: -14.5,
    angularSize: 42,
    earthLat: 19.8207,
    earthLon: -155.4681,
    earthSite: 'Mauna Kea, Hawaii',
    capturedAt: '2025-10-28T10:05:00Z',
    band: 'NIR 3.83–5.00 μm',
  },
  {
    id: 'tile-11',
    title: 'North Ecliptic Pole Calibration',
    imageUrl: TILE_IMAGES[4],
    ra: 180.0,
    dec: 48.0,
    angularSize: 42,
    earthLat: 50.979,
    earthLon: 11.71,
    earthSite: 'Tautenburg, Germany',
    capturedAt: '2025-11-02T01:15:00Z',
    band: 'NIR 0.75–5.0 μm',
  },
  {
    id: 'tile-12',
    title: 'Galactic Center Bulge Cutout',
    imageUrl: TILE_IMAGES[6],
    ra: 266.4,
    dec: -29.0,
    angularSize: 42,
    earthLat: -24.6272,
    earthLon: -70.4042,
    earthSite: 'Paranal, Atacama',
    capturedAt: '2025-11-09T02:55:00Z',
    band: 'NIR 1.64–2.42 μm',
  },
];

export async function fetchSkyGlobeTiles({ signal } = {}) {
  if (!API_BASE) {
    return DEFAULT_GLOBE_TILES;
  }

  const response = await fetch(`${API_BASE}/api/globe/tiles`, {
    signal,
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Globe API responded with ${response.status}`);
  }

  const json = await response.json();
  const list = Array.isArray(json) ? json : json.tiles || [];
  if (!list.length) return DEFAULT_GLOBE_TILES;

  return list.map((item, idx) => ({
    id: item.id ?? `tile-${idx + 1}`,
    title: item.title ?? item.label ?? `Sky Tile #${idx + 1}`,
    imageUrl: item.imageUrl ?? item.image_url ?? item.url ?? TILE_IMAGES[idx % TILE_IMAGES.length],
    ra: Number(item.ra ?? 0),
    dec: Number(item.dec ?? 0),
    angularSize: Number(item.angularSize ?? item.angular_size ?? 40),
    earthLat: Number(item.earthLat ?? item.earth_lat ?? item.lat ?? 0),
    earthLon: Number(item.earthLon ?? item.earth_lon ?? item.lon ?? 0),
    earthSite: item.earthSite ?? item.earth_site ?? item.site ?? 'Earth Ground Station',
    capturedAt: item.capturedAt ?? item.captured_at ?? new Date().toISOString(),
    band: item.band ?? 'NIR 0.75–5.0 μm',
  }));
}

