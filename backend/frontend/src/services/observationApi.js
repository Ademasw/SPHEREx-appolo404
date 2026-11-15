import { loadSequence } from './sequenceClient.js';
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
export const isBackendConfigured = () => true;
export const DEFAULT_FILTER = { enabled: true, model: 'spherex', strength: 100, maskSaturated: true };
export const DEFAULT_SETTINGS = { epoch1Label: 'Epoch 1', epoch1Date: '', epoch2Label: 'Epoch 2', epoch2Date: '', fovArcmin: '6', detectorArray: '6', playerFps: 3, cleanMask: false, smoothDisplay: true };
export function getPlaceholderObservation({ coordinates = '', settings = DEFAULT_SETTINGS } = {}) {
 return { coordinates, source: 'empty', updatedAt: null,
 player: { mode: 'frames', frames: [], videoUrl: null, streamUrl: null, fps: settings.playerFps },
 compare: { epochs: [1,2].map(i => ({ id: String(i), label: settings[`epoch${i}Label`], date: '—', imageUrl: '' })) },
 metadata: { Status: 'Enter coordinates or choose a target to load real observations.' } };
}
export async function fetchObservation(params, options = {}) {
 if (!params.coordinates.trim()) return getPlaceholderObservation(params);
 return loadSequence(params, { ...options, base: API_BASE });
}
// Existing API exposes polling, not SSE/WebSocket.
export const subscribeObservationStream = () => () => {};
