import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const date = value => new Date(value + 'Z').toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
const modes = { comparison: 'Matched pair', preview: 'Raw observations' };

function App() {
  const initial = new URLSearchParams(location.search);
  const [mode, setMode] = useState(initial.get('mode') === 'preview' ? 'preview' : 'comparison');
  const [sequence, setSequence] = useState(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(900);
  const [zoom, setZoom] = useState(1);
  const [contrast, setContrast] = useState(1);
  const [invert, setInvert] = useState(false);
  const [error, setError] = useState('');
  const [imageError, setImageError] = useState(false);
  const [copied, setCopied] = useState(false);
  const loadedInitial = useRef(false);
  const count = sequence?.frames.length || 0;
  const frame = sequence?.frames[index];

  useEffect(() => {
    const abort = new AbortController();
    setPlaying(false); setSequence(null); setError(''); setImageError(false);
    fetch(`/api/${mode}`, { signal: abort.signal }).then(async response => {
      if (!response.ok) throw new Error(response.status === 404 ? 'This observation set has not been prepared yet.' : 'The data service is unavailable.');
      const result = await response.json();
      if (!Array.isArray(result.frames) || !result.frames.length) throw new Error('No observations in this set.');
      setSequence(result);
      const requested = loadedInitial.current ? 0 : Number(initial.get('frame') || 0);
      setIndex(Number.isInteger(requested) && requested >= 0 && requested < result.frames.length ? requested : 0);
      loadedInitial.current = true;
    }).catch(err => { if (err.name !== 'AbortError') setError(err.message); });
    return () => abort.abort();
  }, [mode]);

  useEffect(() => {
    if (!playing || !count) return;
    const timer = setInterval(() => setIndex(current => (current + 1) % count), speed);
    return () => clearInterval(timer);
  }, [playing, speed, count]);

  useEffect(() => {
    if (!sequence) return;
    const query = new URLSearchParams({ mode, frame: String(index) });
    history.replaceState(null, '', `?${query}`);
    sequence.frames.forEach(item => { const image = new Image(); image.src = item.image_url; });
  }, [sequence, mode, index]);

  const step = direction => { setPlaying(false); setIndex(current => (current + direction + count) % count); };
  async function share() {
    try { await navigator.clipboard.writeText(location.href); setCopied(true); setTimeout(() => setCopied(false), 1800); }
    catch { setError('Copy the address from your browser to share this view.'); }
  }

  return <div className="app">
    <header className="topbar"><a className="brand" href="/" aria-label="Apollo 404 home"><span className="orbit">✳</span> APOLLO <b>404</b></a><span className="mission">PLANET X / SPHEREx</span><a className="docs" href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">Data archive ↗</a></header>
    <main>
      <div className="intro"><div><div className="eyebrow"><span/> NASA SPACE APPS CHALLENGE · 2026</div><h1>The sky never<br/><em>stands still.</em></h1><p>Explore real infrared observations. Compare moments.<br className="desktop"/> Look closer at what changes.</p></div><div className="intro-note"><span className="tiny">OBSERVATION WORKSPACE / 001</span><p>404: planet not found<span className="orange">… yet.</span></p><span className="tag">EARLY SCIENCE PREVIEW</span></div></div>
      <section className="workspace" aria-label="Sky observation player">
        <aside className="sidebar"><div className="section-label">01 / REGION</div><h2>WISE 0855 field</h2><p className="muted">A prepared patch of sky around the challenge’s example coordinates.</p><div className="coordinates"><div><span>RA · DEGREES</span><b>{sequence?.query.ra_deg.toFixed(7) || '—'}</b></div><div><span>DEC · DEGREES</span><b>{sequence?.query.dec_deg.toFixed(7) || '—'}</b></div></div><div className="small-row"><span>Field of view</span><b>6 arcmin</b></div><div className="small-row"><span>Instrument</span><b>SPHEREx · D6</b></div><hr/><div className="section-label">02 / OBSERVATIONS</div><div className="mode-buttons">{Object.entries(modes).map(([key, label]) => <button key={key} className={mode === key ? 'selected' : ''} onClick={() => setMode(key)}>{label}<span>{key === 'comparison' ? '02' : '03'}</span></button>)}</div><p className="muted mode-note">{mode === 'comparison' ? 'Two dates with close wavelengths, shared coverage and the supplied zodiacal-light model subtracted.' : 'Three calibrated observations with a shared display scale. Their wavelengths differ; brightness changes may be spectral.'}</p><hr/><div className="section-label">03 / DISPLAY</div><label>Zoom <b>{zoom.toFixed(1)}×</b><input type="range" min="1" max="3" step="0.1" value={zoom} onChange={event => setZoom(Number(event.target.value))}/></label><label>Display contrast <b>{contrast.toFixed(1)}×</b><input type="range" min="0.5" max="2.5" step="0.1" value={contrast} onChange={event => setContrast(Number(event.target.value))}/></label><label className="checkbox"><input type="checkbox" checked={invert} onChange={event => setInvert(event.target.checked)}/> Invert display</label><button className="reset" onClick={() => { setZoom(1); setContrast(1); setInvert(false); }}>Reset display ↺</button></aside>
        <div className="viewer-column"><div className="viewer-heading"><div><span className="live-dot"/> REAL ARCHIVE DATA <span className="release">DR1</span></div><button className="share" onClick={share}>{copied ? 'Link copied ✓' : 'Share view ↗'}</button></div>
          <div className="viewport" aria-live="off"><span className="compass north">N ↑</span><span className="compass east">← E</span><div className="image-window">{frame && !imageError && <img key={frame.image_url} src={frame.image_url} alt={`SPHEREx D6 observation on ${date(frame.time_utc)}; target identification pending`} style={{ transform: `scale(${zoom})`, filter: `contrast(${contrast}) invert(${invert ? 1 : 0})` }} onLoad={() => setImageError(false)} onError={() => { setImageError(true); setPlaying(false); }}/>}{!sequence && !error && <div className="empty">Loading observations<span className="loading-dot">…</span></div>}{error && !sequence && <div className="empty">{error}<small>Check that FastAPI is running and the data are prepared.</small></div>}{imageError && <div className="empty">Image could not be loaded.<small>Try another observation set.</small></div>}</div><div className="viewport-bottom"><span>FIXED SKY GRID</span><span>6.2″ / PIXEL</span></div></div>
          <div className="player"><div className="player-buttons"><button aria-label="Previous frame" disabled={!count} onClick={() => step(-1)}>⏮</button><button className="play" aria-label={playing ? 'Pause animation' : 'Play animation'} disabled={!count || imageError} onClick={() => setPlaying(value => !value)}>{playing ? 'Ⅱ' : '▶'}</button><button aria-label="Next frame" disabled={!count} onClick={() => step(1)}>⏭</button></div><div className="frame-counter"><b>{count ? String(index + 1).padStart(2, '0') : '—'}</b> / {String(count).padStart(2, '0')}<span>OBSERVATION</span></div><label className="speed">Frame interval<select value={speed} onChange={event => setSpeed(Number(event.target.value))}><option value="1500">1.5 seconds</option><option value="900">0.9 seconds</option><option value="400">0.4 seconds</option></select></label></div>
          <div className="timeline" aria-label="Observation dates">{sequence?.frames.map((item, i) => <button key={i} aria-pressed={index === i} className={index === i ? 'active' : ''} onClick={() => { setIndex(i); setPlaying(false); setImageError(false); }}><span className="timeline-dot"/><span>{date(item.time_utc)}</span></button>)}</div>
        </div>
        <aside className="details"><div className="section-label">FRAME DETAILS</div><h3>{frame ? date(frame.time_utc) : 'Awaiting data'}</h3><span className="utc">{frame?.time_utc.slice(11, 19) || '—'} UTC</span><dl><dt>Central wavelength</dt><dd>{frame?.center_wavelength_um.toFixed(5) || '—'} <small>μm</small></dd><dt>Central bandwidth</dt><dd>{frame?.center_bandwidth_um.toFixed(5) || '—'} <small>μm</small></dd><dt>Usable grid</dt><dd>{frame ? ((sequence.processing?.shared_valid_fraction ?? frame.usable_grid_fraction) * 100).toFixed(1) : '—'}<small>%</small></dd></dl><div className="legend"><span/> Masked or uncovered</div><div className="science-note"><span>READ THE SKY CAREFULLY</span><p>These are real observations, but this preview does not confirm a detection or motion of WISE 0855.</p><p>Coordinates follow the challenge example. Target identification is pending.</p></div>{frame && <a className="source-link" href={frame.cutout_url} target="_blank" rel="noreferrer">Download source FITS ↗</a>}</aside>
      </section>
      <div className="footnotes"><p><span>↳</span> Fixed coordinates · north up · east left · shared brightness scale</p><p>NASA/IPAC IRSA data <span> / </span> Apollo 404</p></div>
      {sequence && <details className="processing"><summary>Processing notes & limitations</summary><ul>{sequence.warnings.map(note => <li key={note}>{note}</li>)}</ul><p>Display controls change the rendered image only. They do not modify the original scientific measurements.</p></details>}
      {error && sequence && <p role="status" className="notification">{error}</p>}
    </main><footer><span className="brand small">✳ APOLLO 404</span><span>A little closer to the unknown.</span><span>Built for discovery.</span></footer>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);

