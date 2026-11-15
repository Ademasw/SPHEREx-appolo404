import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { createRoot } from 'react-dom/client';
import './style.css';
import './purple-theme.css';
import { parseViewerQuery, updateViewerQuery } from '../services/viewerQuery.js';

// Presentation-only portal: the same controls keep their original handlers/state.
const controlHost = window.parent !== window ? window.parent.document.getElementById('advanced-controls') : null;
let controlMount = null;
if (controlHost) {
  const shadow = controlHost.shadowRoot || controlHost.attachShadow({ mode: 'open' });
  shadow.replaceChildren();
  document.querySelectorAll('link[rel="stylesheet"], style').forEach(sheet => shadow.append(sheet.cloneNode(true)));
  const style = document.createElement('style');
  style.textContent = `:host { display:block; color:#ece6ff; font-family:Inter,Arial,sans-serif; --line:rgba(190,160,255,.18); --muted:#a99cc8; --orange:#b18aff; } .sidebar { padding:20px 0 0; background:transparent; border:0; width:100%; }`;
  shadow.append(style);
  controlMount = document.createElement('div');
  shadow.append(controlMount);
  document.documentElement.classList.add('archive-embedded');
}
function ArchiveControls({ children }) {
  return controlMount ? createPortal(children, controlMount) : children;
}

const date = value => new Date(value.endsWith('Z') ? value : value + 'Z').toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
const time = value => value.slice(11, 19);
const TARGETS = ["Barnard's Star", 'Epsilon Indi B', 'WISE 0855', 'RW Aurigae', 'R Draconis'];
const DETECTORS = [
  ['D1', '0.75–1.1'], ['D2', '1.1–1.6'], ['D3', '1.6–2.4'], ['D4', '2.4–3.8'], ['D5', '3.8–4.4'], ['D6', '4.4–5.0'],
];
const FOVS = [[0.05, '3′'], [0.1, '6′'], [0.2, '12′']];
const VIEWS = { visits: 'Visit stacks', compare: 'Compare 2 dates', frames: 'All frames', difference: 'Difference' };
const COMPARE_MODES = { side: 'Side by side', blink: 'Blink A ↔ B', diff: 'Difference B − A' };
const PIXEL_ARCSEC = 6.2;
const STAGES = {
  queued: 'Waiting for a free worker',
  searching: 'Asking the IRSA archive which SPHEREx images cover this spot',
  downloading: 'Downloading image cutouts',
  processing: 'Aligning frames on one sky grid',
  rendering: 'Stacking visits and drawing images',
};

function readUrl() {
  try {
    const value = parseViewerQuery(location.search);
    return { ...value, q: value.q || 'WISE 0855', det: value.det === 'all' ? `D${value.displayDetector}` : value.det };
  } catch (error) {
    return { q: '', det: 'D6', fov: .1, view: 'visits', frame: 0, a: null, b: null, cmp: 'side', bg: 'model', clean: false, smooth: true, error: error.message };
  }
}

function App() {
  const initial = useMemo(readUrl, []);
  const [input, setInput] = useState(initial.q);
  const [request, setRequest] = useState({ q: initial.q, det: initial.det, fov: initial.fov, clean: initial.clean, smooth: initial.smooth, bg: initial.bg });
  const [job, setJob] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [view, setView] = useState(initial.view);
  const [index, setIndex] = useState(initial.frame);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(700);
  const [zoom, setZoom] = useState(1);
  const [contrast, setContrast] = useState(1);
  const [invert, setInvert] = useState(false);
  const [showMarker, setShowMarker] = useState(true);
  const [imageError, setImageError] = useState(false);
  const [copied, setCopied] = useState(false);
  const firstLoad = useRef(true);
  const [pairA, setPairA] = useState(initial.a);
  const [pairB, setPairB] = useState(initial.b);
  const [compareMode, setCompareMode] = useState(initial.cmp);
  const [showB, setShowB] = useState(false);

  const visits = manifest?.visits || [];
  const items = !manifest ? [] : view === 'visits' ? visits : view === 'frames' ? manifest.frames
    : view === 'compare' ? [] : manifest.difference ? [{ ...manifest.difference, kind: 'difference' }] : [];
  const a = visits.length ? Math.min(pairA ?? 0, visits.length - 1) : 0;
  const b = visits.length ? Math.min(pairB ?? visits.length - 1, visits.length - 1) : 0;
  const visitA = visits[a];
  const visitB = visits[b];
  const pairUrl = manifest && visitA && visitB && a !== b
    ? `/api/sequence/${manifest.query.key}/${manifest.query.detector}/pair/${a}/${b}.png` : null;
  const count = items.length;
  const item = items[Math.min(index, Math.max(count - 1, 0))];
  const imageUrl = item?.image_url;
  const target = manifest?.target;
  const marker = !showMarker || !item || view === 'difference' ? null
    : item.predicted_position?.display_fraction || { x: 0.5, y: 0.5 };

  // Fetch the sequence; while the server is processing (HTTP 202), poll for progress.
  useEffect(() => {
    let cancelled = false; let timer;
    const abort = new AbortController();
    if (initial.error) { setJob({ status: 'error', error: initial.error }); return; }
    setManifest(null); setJob({ status: 'queued', stage: 'searching' }); setPlaying(false); setImageError(false);
    const params = new URLSearchParams({ q: request.q, det: request.det, fov: String(request.fov), bg: request.bg, clean: String(request.clean), smooth: String(request.smooth) });
    const poll = async () => {
      try {
        const response = await fetch(`/api/sequence?${params}`, { signal: abort.signal });
        const body = await response.json().catch(() => ({}));
        if (cancelled) return;
        if (response.status === 200 && body.manifest) {
          setManifest(body.manifest); setJob(null);
          const keep = firstLoad.current;
          firstLoad.current = false;
          const preferred = keep ? initial.view : view;
          const next = preferred === 'visits' && !body.manifest.visits.length ? 'frames' : preferred;
          setView(next === 'compare' && body.manifest.visits.length < 2 ? 'frames' : next);
          if (!keep) { setIndex(0); setPairA(0); setPairB(Math.max(0, body.manifest.visits.length - 1)); }
        } else if (response.status === 202) {
          setJob(body); timer = setTimeout(poll, 1200);
        } else {
          setJob({ status: 'error', error: body.error || body.detail || 'The data service is unavailable.' });
        }
      } catch (err) {
        if (err.name !== 'AbortError' && !cancelled) setJob({ status: 'error', error: 'The data service is unavailable.' });
      }
    };
    poll();
    return () => { cancelled = true; clearTimeout(timer); abort.abort(); };
  }, [request]);

  useEffect(() => {  // Blink A <-> B in the compare view
    if (view !== 'compare' || compareMode !== 'blink' || !playing) return;
    const timer = setInterval(() => setShowB(current => !current), speed);
    return () => clearInterval(timer);
  }, [view, compareMode, playing, speed]);

  useEffect(() => {
    if (view === 'compare' || !playing || count < 2) return;
    const timer = setInterval(() => setIndex(current => (current + 1) % count), speed);
    return () => clearInterval(timer);
  }, [playing, speed, count]);

  useEffect(() => {
    if (initial.error) return;
    const search = updateViewerQuery(location.search, { q: request.q, det: initial.det === 'all' ? 'all' : request.det, fov: request.fov, bg: request.bg, clean: request.clean, smooth: request.smooth, view,
      ...(view === 'compare' ? { a, b, cmp: compareMode, frame: null } : { frame: index, a: null, b: null, cmp: null }) });
    history.replaceState(null, '', search);
    if (window.parent !== window) window.parent.postMessage({ type: 'archive-state', search }, window.location.origin);
  }, [request, view, index, a, b, compareMode]);

  useEffect(() => {  // preload so the flipbook does not flicker
    items.forEach(entry => { const image = new Image(); image.src = entry.image_url; });
  }, [manifest, view]);

  const search = (q, overrides = {}) => {
    const next = { ...request, q: q.trim() || request.q, ...overrides };
    setInput(next.q);
    setRequest(next);
  };
  const step = direction => { setPlaying(false); setIndex(current => (current + direction + count) % count); };
  const choose = next => { setView(next); setIndex(0); setPlaying(false); setImageError(false); setShowB(false); };
  async function share() {
    try { const url = new URL('/dashboard/advanced', location.origin); url.search = location.search; await navigator.clipboard.writeText(url.href); setCopied(true); setTimeout(() => setCopied(false), 1800); }
    catch { /* the address bar holds the same link */ }
  }

  const resolved = manifest ? manifest.target || null : job?.resolved;
  const center = manifest?.query || (job?.resolved && { ra_deg: job.resolved.ra_deg, dec_deg: job.resolved.dec_deg });
  const counts = manifest?.archive.observations_by_detector;
  const processing = manifest?.processing;

  return <div className="app">
    <header className="topbar"><a className="brand" href="/" target="_top">SPHERA HUNTER</a><a className="docs" href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">NASA / IPAC IRSA ↗</a></header>
    <main>

      <form className="search" onSubmit={event => { event.preventDefault(); search(input); }}>
        <label htmlFor="q" className="section-label">SKY POSITION</label>
        <div className="search-row"><input id="q" value={input} onChange={event => setInput(event.target.value)} placeholder="Name, or RA Dec: 133.7951 -7.2451 · 08h55m10.8s -07d14m42s" autoComplete="off" spellCheck="false"/><button type="submit">Show the sky ↗</button></div>
        <div className="chips"><span>Try:</span>{TARGETS.map(name => <button type="button" key={name} className={request.q === name ? 'selected' : ''} onClick={() => search(name)}>{name}</button>)}</div>
      </form>

      <section className="workspace" aria-label="Sky observation player">
        <ArchiveControls><aside className="sidebar">
          <div className="section-label">01 / REGION</div>
          <h2>{resolved?.name || request.q}</h2>
          <p className="muted">{resolved?.pmra != null ? `Catalog position moved to ${resolved.position_epoch} with its proper motion (${(Math.hypot(resolved.pmra, resolved.pmdec) / 1000).toFixed(2)}″/yr).` : 'Fixed sky position.'}</p>
          <div className="coordinates"><div><span>RA · DEGREES</span><b>{center ? center.ra_deg.toFixed(4) : '—'}</b></div><div><span>DEC · DEGREES</span><b>{center ? center.dec_deg.toFixed(4) : '—'}</b></div></div>
          <div className="section-label">DETECTOR · WAVELENGTH μm</div>
          <div className="detectors">{DETECTORS.map(([d, range]) => <button key={d} className={request.det === d ? 'selected' : ''} onClick={() => search(request.q, { det: d })} title={`${range} μm`}><b>{d}</b><span>{range}</span>{counts && <small>{counts[d]} img</small>}</button>)}</div>
          <div className="small-row"><span>Field of view</span><span className="fov">{FOVS.map(([f, label]) => <button key={f} className={request.fov === f ? 'selected' : ''} onClick={() => search(request.q, { fov: f })}>{label}</button>)}</span></div>
          <hr/>
          <div className="section-label">02 / SHOW</div>
          <div className="mode-buttons">{Object.entries(VIEWS).map(([key, label]) => {
            const n = !manifest ? '' : key === 'visits' ? visits.length : key === 'compare' ? (visits.length >= 2 ? 2 : 0) : key === 'frames' ? manifest.frames.length : manifest.difference ? 1 : 0;
            return <button key={key} disabled={manifest && !n} className={view === key ? 'selected' : ''} onClick={() => choose(key)}>{label}<span>{n === '' ? '' : String(n).padStart(2, '0')}</span></button>;
          })}</div>
          <p className="muted mode-note">{view === 'compare' ? 'Pick two visits. See them side by side, blink between them, or subtract them: a moving star leaves a black and white pair.' : view === 'visits' ? 'SPHEREx returns to each spot about every six months. Available selected frames of one visit are aligned and averaged. Blinking visits helps inspect changes; wavelengths and image quality can also affect the result.' : view === 'frames' ? 'Selected usable exposures in time order. Each frame can sample a different wavelength of the detector band.' : 'Last visit minus first visit. A moving star leaves a black and white pair; a variable star a single spot.'}</p>
          <label className="checkbox"><input type="checkbox" checked={showMarker} onChange={event => setShowMarker(event.target.checked)}/> {target ? `Propagated position · ${target.motion_source || target.source || 'catalog'}` : 'Mark search position'}</label>
          <hr/>
          <div className="section-label">03 / DISPLAY</div>
          <label>Zoom <b>{zoom.toFixed(1)}×</b><input type="range" min="1" max="3" step="0.1" value={zoom} onChange={event => setZoom(Number(event.target.value))}/></label>
          <label>Display contrast <b>{contrast.toFixed(1)}×</b><input type="range" min="0.5" max="2.5" step="0.1" value={contrast} onChange={event => setContrast(Number(event.target.value))}/></label>
          <label className="checkbox"><input type="checkbox" checked={invert} onChange={event => setInvert(event.target.checked)}/> Invert display</label>
          <button className="reset" onClick={() => { setZoom(1); setContrast(1); setInvert(false); }}>Reset display ↺</button>
        </aside></ArchiveControls>

        <div className="viewer-column">
          <div className="viewer-heading"><div><span className="live-dot"/> REAL ARCHIVE DATA <span className="release">DR1 + QR3</span></div><button className="share" onClick={share}>{copied ? 'Link copied ✓' : 'Share view ↗'}</button></div>
          <div className="viewport" aria-live="polite">
            <span className="compass north">N ↑</span><span className="compass east">← E</span>
            <div className={view === 'compare' ? 'image-window wide' : 'image-window'}>
              {view === 'compare' && visitA && visitB && <Compare {...{ mode: compareMode, visitA, visitB, showB, pairUrl, zoom, contrast, invert, showMarker, detector: request.det }}/>}
              {manifest && item && !imageError && <div className="frame-wrap" style={{ transform: `scale(${zoom})` }}>
                <img key={imageUrl} src={imageUrl} alt={view === 'difference' ? 'Difference between the last and first visit' : `SPHEREx ${request.det} ${view === 'visits' ? 'visit stack' : 'frame'} from ${date(item.time_utc)}`} style={{ filter: `contrast(${contrast}) invert(${invert ? 1 : 0})` }} onError={() => { setImageError(true); setPlaying(false); }}/>
                {marker && <span className={`marker ${item.predicted_position ? `marker--${String(item.predicted_position.source || 'catalog').toLowerCase().replace(/\s+/g, '-')}` : 'marker--query'}`} style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }} aria-label={item.predicted_position ? `${item.predicted_position.source} propagated position` : 'Requested coordinate'} />}
              </div>}
              {job && job.status !== 'error' && <div className="empty progress"><b>{STAGES[job.stage] || 'Working'}</b>{job.total > 1 && <><div className="bar"><span style={{ width: `${Math.round(100 * job.done / job.total)}%` }}/></div><small>{job.done} / {job.total}</small></>}<small>First look at a new spot takes up to a minute: the archive is queried live. Once processed, it opens instantly.</small></div>}
              {job?.status === 'error' && <div className="empty">{job.error}<small>Check the input, or try again in a moment: the NASA archive is shared by many users.</small></div>}
              {manifest && !count && view !== 'compare' && <div className="empty">Nothing to show in this mode.<small>Try “All frames” or another detector.</small></div>}
              {imageError && <div className="empty">Image could not be loaded.<small>Try again in a moment.</small></div>}
            </div>
            <div className="viewport-bottom"><span>FIXED SKY GRID · {FOVS.find(([f]) => f === request.fov)?.[1]} FIELD</span><span>6.2″ / PIXEL</span></div>
          </div>
          {view === 'compare' && visits.length >= 2 ? <div className="player compare-bar">
            <div className="segmented" role="tablist">{Object.entries(COMPARE_MODES).map(([key, label]) => <button key={key} role="tab" aria-selected={compareMode === key} className={compareMode === key ? 'selected' : ''} onClick={() => { setCompareMode(key); setPlaying(key === 'blink'); setShowB(false); }}>{label}</button>)}</div>
            <label className="pick"><span>A</span><select value={a} onChange={event => setPairA(Number(event.target.value))}>{visits.map((v, i) => <option key={i} value={i} disabled={i === b}>{date(v.time_utc)}</option>)}</select></label>
            <button className="swap" aria-label="Swap A and B" onClick={() => { setPairA(b); setPairB(a); }}>⇄</button>
            <label className="pick"><span>B</span><select value={b} onChange={event => setPairB(Number(event.target.value))}>{visits.map((v, i) => <option key={i} value={i} disabled={i === a}>{date(v.time_utc)}</option>)}</select></label>
            {compareMode === 'blink' && <button className="play" aria-label={playing ? 'Pause' : 'Play'} onClick={() => setPlaying(value => !value)}>{playing ? 'Ⅱ' : '▶'}</button>}
          </div> : <div className="player">
            <div className="player-buttons"><button aria-label="Previous" disabled={count < 2} onClick={() => step(-1)}>⏮</button><button className="play" aria-label={playing ? 'Pause' : 'Play'} disabled={count < 2 || imageError} onClick={() => setPlaying(value => !value)}>{playing ? 'Ⅱ' : '▶'}</button><button aria-label="Next" disabled={count < 2} onClick={() => step(1)}>⏭</button></div>
            <div className="frame-counter"><b>{count ? String(Math.min(index, count - 1) + 1).padStart(2, '0') : '—'}</b> / {String(count).padStart(2, '0')}<span>{view === 'visits' ? 'VISIT' : view === 'frames' ? 'FRAME' : 'DIFFERENCE'}</span></div>
            <label className="speed">Frame interval<select value={speed} onChange={event => setSpeed(Number(event.target.value))}><option value="1200">1.2 seconds</option><option value="700">0.7 seconds</option><option value="350">0.35 seconds</option><option value="150">0.15 seconds</option></select></label>
          </div>}
          {view === 'visits' && <div className="timeline" aria-label="Visits">{items.map((entry, i) => <button key={i} aria-pressed={index === i} className={index === i ? 'active' : ''} onClick={() => { setIndex(i); setPlaying(false); }}><span className="timeline-dot"/><span>{date(entry.time_utc)}</span></button>)}</div>}
          {view === 'frames' && count > 0 && <div className="scrubber"><input type="range" min="0" max={count - 1} value={Math.min(index, count - 1)} onChange={event => { setIndex(Number(event.target.value)); setPlaying(false); }} aria-label="Frame"/><div className="scrubber-dates"><span>{date(items[0].time_utc)}</span><span>{date(items[count - 1].time_utc)}</span></div></div>}
        </div>

        <aside className="details">
          <div className="section-label">{view === 'compare' ? 'COMPARISON' : view === 'visits' ? 'VISIT DETAILS' : view === 'frames' ? 'FRAME DETAILS' : 'DIFFERENCE'}</div>
          {view === 'compare' && visitA && visitB ? <ComparisonDetails visitA={visitA} visitB={visitB} target={target}/> : view === 'difference' && manifest?.difference ? <>
            <h3>{date(manifest.difference.from_utc)} → {date(manifest.difference.to_utc)}</h3>
            <p className="muted">{manifest.difference.description}</p>
          </> : <>
            <h3>{item ? date(item.time_utc) : 'Awaiting data'}</h3>
            <span className="utc">{item ? (view === 'visits' ? `${date(item.time_start_utc)} – ${date(item.time_end_utc)}` : `${time(item.time_utc)} UTC · ${item.release}`) : '—'}</span>
            <dl>{view === 'visits' ? <>
              <dt>Frames stacked</dt><dd>{item?.n_frames ?? '—'}</dd>
              <dt>Wavelength range</dt><dd>{item?.wavelength_min_um != null ? `${item.wavelength_min_um.toFixed(2)}–${item.wavelength_max_um.toFixed(2)}` : '—'} <small>μm</small></dd>
            </> : <>
              <dt>Wavelength at center</dt><dd>{item?.wavelength_um != null ? item.wavelength_um.toFixed(3) : '—'} <small>μm</small></dd>
              <dt>Visit</dt><dd>{item ? item.visit + 1 : '—'}</dd>
            </>}
              <dt>Sky covered</dt><dd>{item ? (item.usable_grid_fraction * 100).toFixed(0) : '—'}<small>%</small></dd></dl>
          </>}
          <div className="science-note"><span>POSITION &amp; DATA QUALITY</span>
            {view === 'compare' ? <p>Both images share a sky grid. Differences can also reflect wavelength coverage, noise, artifacts, saturation or the PSF; they are not automatic motion detections.</p> : target && item?.predicted_position && view !== 'difference' ? <p>Reference position propagated with {item.predicted_position.source || target.motion_source || target.source || 'catalog astrometry'}. The marker is a coordinate reference, not a source detection.{item.measured_position && ` Local measured peak: ${(Math.hypot(item.measured_position.x - item.predicted_position.grid_pixel.x, item.measured_position.y - item.predicted_position.grid_pixel.y) * 6.2).toFixed(1)}″ away; S/N ${item.measured_position.peak_snr.toFixed(0)}.`}</p>
              : <p>This is a requested sky coordinate without a matched proper-motion source. A bright pixel is not automatically a confirmed object; compare visits and wavelengths.</p>}
            {processing && <p>{processing.frames_used} of {processing.frames_available} archive frames used{processing.frames_failed ? `; ${processing.frames_failed} could not be fetched (archive busy)` : ''}.</p>}
          </div>
          {view === 'compare' && visitA && visitB ? <>
            <a className="source-link" href={visitA.cutout_url} target="_blank" rel="noreferrer">Source FITS, visit A ↗</a>
            <a className="source-link" href={visitB.cutout_url} target="_blank" rel="noreferrer">Source FITS, visit B ↗</a>
          </> : item?.cutout_url && <a className="source-link" href={item.cutout_url} target="_blank" rel="noreferrer">Download source FITS ↗</a>}
          {manifest && <a className="source-link" href="https://irsa.ipac.caltech.edu/applications/spherex" target="_blank" rel="noreferrer">IRSA SPHEREx Data Explorer ↗</a>}
        </aside>
      </section>
      <div className="footnotes"><p><span>↳</span> North up · east left · one brightness scale per mode · saturated star cores drawn white</p><p>NASA/IPAC IRSA · SPHEREx DR1 + QR3 <span> / </span> Apollo 404</p></div>
      {manifest && <details className="processing"><summary>How these images are made</summary><ul>{manifest.processing.steps.map(note => <li key={note}>{note}</li>)}{manifest.warnings.map(note => <li key={note}>{note}</li>)}</ul><p>Display controls change only the picture, never the measurements.</p></details>}
    </main><footer><span className="brand small">✳ APOLLO 404</span><span>A little closer to the unknown.</span><span>Built for discovery.</span></footer>
  </div>;
}

function Panel({ label, visit, src, zoom, contrast, invert, marker, alt }) {
  return <figure className="compare-panel">
    <figcaption><b>{label}</b>{visit ? <> {date(visit.time_utc)} <small>· {visit.n_frames} frames</small></> : null}</figcaption>
    <div className="compare-frame"><div className="frame-wrap" style={{ transform: `scale(${zoom})` }}>
      <img src={src} alt={alt} style={{ filter: `contrast(${contrast}) invert(${invert ? 1 : 0})` }}/>
      {marker && <span className={marker.center ? 'marker center' : 'marker'} style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }} aria-hidden="true"/>}
    </div></div>
  </figure>;
}

function markerFor(visit, show) {
  if (!show) return null;
  return visit.predicted_position?.display_fraction || { x: 0.5, y: 0.5, center: true };
}

function Compare({ mode, visitA, visitB, showB, pairUrl, zoom, contrast, invert, showMarker, detector }) {
  const common = { zoom, contrast, invert };
  if (mode === 'diff') {
    return <div className="compare-grid single">
      {pairUrl ? <Panel label="B − A" visit={null} src={pairUrl} {...common} marker={null} alt={`Visit ${date(visitB.time_utc)} minus visit ${date(visitA.time_utc)}`}/>
        : <div className="empty">Choose two different visits.</div>}
    </div>;
  }
  if (mode === 'blink') {
    const visit = showB ? visitB : visitA;
    return <div className="compare-grid single">
      <Panel label={showB ? 'B' : 'A'} visit={visit} src={visit.image_url} {...common} marker={markerFor(visit, showMarker)} alt={`SPHEREx ${detector} visit stack from ${date(visit.time_utc)}`}/>
    </div>;
  }
  return <div className="compare-grid">
    <Panel label="A" visit={visitA} src={visitA.image_url} {...common} marker={markerFor(visitA, showMarker)} alt={`SPHEREx ${detector} visit stack from ${date(visitA.time_utc)}`}/>
    <Panel label="B" visit={visitB} src={visitB.image_url} {...common} marker={markerFor(visitB, showMarker)} alt={`SPHEREx ${detector} visit stack from ${date(visitB.time_utc)}`}/>
  </div>;
}

function ComparisonDetails({ visitA, visitB, target }) {
  const days = (new Date(visitB.time_utc + 'Z') - new Date(visitA.time_utc + 'Z')) / 86400000;
  const pa = visitA.predicted_position, pb = visitB.predicted_position;
  const predicted = pa && pb ? Math.hypot((pb.ra_deg - pa.ra_deg) * Math.cos(pa.dec_deg * Math.PI / 180), pb.dec_deg - pa.dec_deg) * 3600 : null;
  const ma = visitA.measured_position, mb = visitB.measured_position;
  const measured = ma && mb ? Math.hypot(mb.x - ma.x, mb.y - ma.y) * PIXEL_ARCSEC : null;
  const range = v => v.wavelength_min_um != null ? `${v.wavelength_min_um.toFixed(2)}–${v.wavelength_max_um.toFixed(2)} μm` : '—';
  return <>
    <h3>{date(visitA.time_utc)} → {date(visitB.time_utc)}</h3>
    <span className="utc">{Math.abs(days) >= 60 ? `${(Math.abs(days) / 365.25).toFixed(2)} years apart` : `${Math.round(Math.abs(days))} days apart`}</span>
    <dl>
      <dt>Frames stacked · A / B</dt><dd>{visitA.n_frames} / {visitB.n_frames}</dd>
      <dt>Wavelengths · A</dt><dd className="small-dd">{range(visitA)}</dd>
      <dt>Wavelengths · B</dt><dd className="small-dd">{range(visitB)}</dd>
      {predicted != null && <><dt>Expected shift · {target?.name}</dt><dd>{predicted.toFixed(1)}<small>″ = {(predicted / PIXEL_ARCSEC).toFixed(2)} px</small></dd></>}
      {measured != null && <><dt>Measured shift near ring</dt><dd>{measured.toFixed(1)}<small>″</small></dd></>}
    </dl>
  </>;
}

createRoot(document.getElementById('root')).render(<App/>);
