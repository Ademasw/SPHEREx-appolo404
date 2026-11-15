import { normalizeSequence } from './sequenceAdapter.js';
async function request(path, signal, base, fetchImpl, method = 'GET') {
 const response = await fetchImpl(base + path, { signal, method, headers: { Accept: 'application/json' } });
 let data;
 try { data = await response.json(); }
 catch { throw new Error(`The server returned an unreadable response (${response.status}). Please retry; if it continues, check the backend log.`); }
 if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.error || `API error ${response.status}`);
 return data;
}
function pause(signal) {
 return new Promise((resolve, reject) => {
   const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
   const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, 1500);
   if (signal?.aborted) abort(); else signal?.addEventListener('abort', abort, { once: true });
 });
}
export async function loadSequence(params, { signal, base = '', fetchImpl = fetch, wait = pause, refresh = false } = {}) {
 const settings = params.settings;
 const fov = Number(settings.fovArcmin) / 60;
 if (![0.05, 0.1, 0.2].includes(fov)) throw new Error('Supported fields of view: 3, 6 or 12 arcmin.');
 const detectors = settings.detectorArray === 'all' ? [1,2,3,4,5,6] : [Number(settings.detectorArray)];
 if (detectors.some(det => !Number.isInteger(det) || det < 1 || det > 6)) throw new Error('Select detector D1 to D6, or all.');
 const states = [];
 // Sequential scheduling avoids flooding the existing bounded worker pool.
 for (const det of detectors) {
  const query = new URLSearchParams({ q: params.coordinates, det: `D${det}`, fov: String(fov), bg: params.filter?.enabled === false ? 'none' : params.filter?.background || 'model', clean: String(Boolean(settings.cleanMask)), smooth: String(settings.smoothDisplay !== false) });
  const deadline = Date.now() + 20 * 60 * 1000;
  let force = refresh;
  while (true) {
   signal?.throwIfAborted();
   const state = await request(`/api/sequence${force ? '/refresh' : ''}?${query}`, signal, base, fetchImpl, force ? 'POST' : 'GET');
   force = false;
   if (state.status === 'done') { states.push(state); break; }
   if (state.status === 'error') throw new Error(state.error || 'Processing failed');
   if (!['queued', 'running'].includes(state.status)) throw new Error('Unexpected processing state returned by server.');
   if (Date.now() > deadline) throw new Error('Processing is taking longer than 20 minutes. Submit again to check the cached job.');
   await wait(signal);
  }
 }
 return normalizeSequence(states, params, path => base + path);
}
