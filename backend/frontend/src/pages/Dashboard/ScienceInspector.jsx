import { useEffect, useState, useRef } from 'react';
import { API_BASE } from '../../services/observationApi.js';
import { useLocation, useNavigate } from 'react-router-dom';

async function get(path, signal) {
  const response = await fetch(API_BASE + path, { signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Numerical product unavailable');
  return data;
}

export default function ScienceInspector({ observation, status }) {
  const location = useLocation(), navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const key = observation.science?.sequenceKey;
  const detector = observation.metadata?.['Displayed Detector'];
  const [coverage, setCoverage] = useState(null);
  const [index, setIndex] = useState(0);
  const [mask, setMask] = useState(false);
  const [pixel, setPixel] = useState(null);
  const [spectrum, setSpectrum] = useState(null);
  const [error, setError] = useState('');
  const [download, setDownload] = useState('');
  const [busy, setBusy] = useState(false);
  const [bandError, setBandError] = useState(false);
  const activeRequest = useRef(null);
  const [catalogs, setCatalogs] = useState({gaia:false,wise:false});
  const [catalogData, setCatalogData] = useState({});
  const [catalogErrors, setCatalogErrors] = useState({});
  const [selectedCatalog, setSelectedCatalog] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    setCatalogData({}); setCatalogErrors({}); setSelectedCatalog(null);
    if (key && status === 'ready') for (const type of ['gaia','wise']) {
      if (!catalogs[type]) continue;
      const frameIndex = coverage?.frames[index]?.index;
      if (frameIndex === undefined) continue;
      get(`/api/science/${key}/catalog?det=${detector}&index=${frameIndex}&catalog=${type}`, controller.signal)
        .then(data => {if (!controller.signal.aborted) setCatalogData(current => ({...current,[type]:data}));})
        .catch(error => {if (error.name !== 'AbortError') setCatalogErrors(current => ({...current,[type]:error.message}));});
    }
    return () => controller.abort();
  }, [key, detector, status, index, coverage, catalogs]);
  useEffect(() => () => activeRequest.current?.abort(), [key, detector, index]);
  useEffect(() => {
    setCoverage(null); setPixel(null); setSpectrum(null); setError(''); setIndex(0);
    if (!key || status !== 'ready') return;
    const controller = new AbortController();
    get(`/api/science/${key}/coverage?det=${detector}`, controller.signal).then(setCoverage)
      .catch(error => { if (error.name !== 'AbortError') setError(error.message); });
    return () => controller.abort();
  }, [key, detector, status]);
  if (!key || status !== 'ready') return null;
  const frame = coverage?.frames[index];
  const crop = coverage?.display?.crop || {x0:0,y0:0,x1:coverage?.grid.size_px,y1:coverage?.grid.size_px};
  const low = params.get('wmin'), high = params.get('wmax');
  const bandQuery = low && high && frame?.visit != null ? `det=${detector}&visit=${frame.visit}&low=${encodeURIComponent(low)}&high=${encodeURIComponent(high)}` : '';
  const inspect = async event => {
    if (!frame || busy) return;
    const box = event.currentTarget.getBoundingClientRect();
    const crop = coverage.display?.crop || { x0:0, y0:0, x1:coverage.grid.size_px, y1:coverage.grid.size_px };
    const x = Math.min(crop.x1 - 1, crop.x0 + Math.floor((event.clientX - box.left) / box.width * (crop.x1 - crop.x0)));
    const y = Math.max(crop.y0, crop.y1 - 1 - Math.floor((event.clientY - box.top) / box.height * (crop.y1 - crop.y0)));
    setBusy(true); setError(''); setSpectrum(null); setDownload('');
    activeRequest.current?.abort();
    const controller = new AbortController(); activeRequest.current = controller;
    try {
      const result = await get(`/api/science/${key}/pixel?det=${detector}&index=${frame.index}&x=${x}&y=${y}`, controller.signal);
      if (controller.signal.aborted) return;
      setPixel(result);
      if (frame.visit !== null) {
        const path = `/api/science/${key}/aperture?det=${detector}&x=${x}&y=${y}&visit=${frame.visit}`;
        const result = await get(path, controller.signal);
        if (controller.signal.aborted) return;
        setSpectrum(result); setDownload(API_BASE + path);
      }
    } catch (error) { if (error.name !== 'AbortError') setError(error.message); }
    finally { setBusy(false); }
  };
  const points = spectrum?.points || [];
  const waves = points.map(p => p.wavelength_um), fluxes = points.flatMap(p => [p.flux - p.uncertainty, p.flux + p.uncertainty]);
  const lo = Math.min(...waves), hi = Math.max(...waves), bottom = Math.min(...fluxes), top = Math.max(...fluxes);
  const sx = v => 50 + (v - lo) / (hi - lo || 1) * 550, sy = v => 180 - (v - bottom) / (top - bottom || 1) * 150;
  return <details className="panel" style={{ padding:20, marginTop:20 }}>
    <summary>Numerical inspection · wavelength coverage · quality · preliminary spectrum</summary>
    {error && <p role="alert">{error}</p>}
    {!frame && <p>Refresh this field in Explore to prepare numerical wavelength maps.</p>}
    {frame && <>
      <p>Individual detector exposures; nominal 102-channel calibration assignments are not yet available. Missing wavelengths remain missing.</p>
      <p><a target="_blank" rel="noreferrer" href={'https://aladin.cds.unistra.fr/AladinLite/?' + new URLSearchParams({target:`${coverage.grid.header.CRVAL1} ${coverage.grid.header.CRVAL2}`,fov:String(coverage.grid.size_px * 6.2 / 3600),survey:'P/allWISE/color'})}>Open this sky field in Aladin / AllWISE</a> (separate survey and epochs).</p>
      <label>Exposure <select value={index} onChange={e => {setIndex(Number(e.target.value));setPixel(null);setSpectrum(null);}}>
        {coverage.frames.map((f,i) => <option key={f.index} value={i}>{f.time_utc} UTC · visit {f.visit ?? 'unstacked'} · {f.min_um?.toFixed(3) ?? '—'}–{f.max_um?.toFixed(3) ?? '—'} μm · {(f.usable_fraction * 100).toFixed(1)}% usable</option>)}
      </select></label>
      <p><label><input type="checkbox" checked={mask} onChange={e => setMask(e.target.checked)} /> Show excluded-pixel overlay (amber)</label></p>
      <p>{['gaia','wise'].map(type => <label key={type} style={{marginRight:20}}><input type="checkbox" checked={catalogs[type]} onChange={e => setCatalogs(current => ({...current,[type]:e.target.checked}))}/>{type === 'gaia' ? 'Gaia DR3 (cyan)' : 'AllWISE (green)'}</label>)}</p>
      {Object.entries(catalogErrors).map(([type,error]) => <p role="alert" key={type}>{type}: {error}. SPHEREx data remain available.</p>)}
      {Object.values(catalogData).map(data => <p key={data.catalog}>{data.catalog}: {data.sources.length} markers. {data.truncated && 'Catalogue row limit exceeded; overlay is incomplete.'} {data.limitations}</p>)}
      <form onSubmit={event => { event.preventDefault(); const data=new FormData(event.currentTarget); const query=new URLSearchParams(location.search); query.set('wmin',data.get('low'));query.set('wmax',data.get('high'));setBandError(false);navigate({pathname:location.pathname,search:'?'+query}); }}>
        <label>Wavelength min (μm) <input key={'lo'+low+index} name="low" type="number" step="any" min="0.7" max="5.1" required defaultValue={low || frame.min_um || ''}/></label>
        <label> max (μm) <input key={'hi'+high+index} name="high" type="number" step="any" min="0.7" max="5.1" required defaultValue={high || frame.max_um || ''}/></label>
        <button disabled={frame.visit == null}>Show selected spectral range</button>
      </form>
      {bandQuery && <div><p>Selected spectral range, visit {frame.visit}; local wavelength centers selected per pixel. Diagnostic stack, separate from the broadband exposure below.</p>
        <img src={`${API_BASE}/api/science/${key}/band.png?${bandQuery}`} alt="Selected spectral range; unavailable ranges contain no measurements" onError={() => setBandError(true)} onLoad={() => setBandError(false)} style={{maxWidth:470,width:'100%'}}/>
        {bandError && <p role="alert">No compatible measurements, or spectral product unavailable. Choose another interval or refresh this field.</p>}
        <a href={`${API_BASE}/api/science/${key}/band.fits?${bandQuery}`}>Export spectral image, diagonal variance and contributions (FITS)</a>
      </div>}
      <div style={{position:'relative',width:470,maxWidth:'100%'}}>
        <img src={API_BASE + frame.image_url} alt="Click a SPHEREx exposure to inspect numerical pixels" onClick={inspect} style={{width:'100%',display:'block',cursor:'crosshair'}} />
        {mask && frame.mask_url && <img src={API_BASE + frame.mask_url} alt="Amber marks the selected exclusion policy" style={{position:'absolute',inset:0,width:'100%',mixBlendMode:'screen',pointerEvents:'none'}} />}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Catalogue markers on SPHEREx sky coordinates" style={{position:'absolute',inset:0,width:'100%',height:'100%',pointerEvents:'none'}}>
          {Object.entries(catalogData).flatMap(([type,data]) => data.sources.map(source => <circle key={type+source.id} cx={(source.grid_x+.5-crop.x0)/(crop.x1-crop.x0)*100} cy={(crop.y1-source.grid_y-.5)/(crop.y1-crop.y0)*100} r="1" fill="none" stroke={type==='gaia'?'cyan':'lime'} strokeWidth=".35" style={{pointerEvents:'all',cursor:'pointer'}} onClick={() => setSelectedCatalog(source)}><title>{data.catalog}: {source.id}</title></circle>))}
        </svg>
      </div>
      {selectedCatalog && <p>Catalogue object: {selectedCatalog.catalog} {selectedCatalog.id} · ICRS {selectedCatalog.ra_deg.toFixed(6)}, {selectedCatalog.dec_deg.toFixed(6)}° · magnitude {selectedCatalog.magnitude ?? 'unknown'} · reference epoch {selectedCatalog.reference_epoch ?? 'unavailable'} · proper motion {selectedCatalog.proper_motion_applied ? 'propagated to observation' : 'not applied'} · RUWE {selectedCatalog.ruwe ?? 'unknown'} · contamination flags {selectedCatalog.cc_flags ?? 'not supplied'}.</p>}
      <p>Click the image for sky coordinates, values and original flags. The preview is north up and east left. {busy && 'Reading numerical measurements…'}</p>
      {frame.data_url && <a href={API_BASE + frame.data_url}>Download numerical arrays, wavelengths and raw FLAGS (NPZ)</a>}
      {pixel && <p>ICRS {pixel.ra_deg.toFixed(6)}, {pixel.dec_deg.toFixed(6)}° · pixel ({pixel.x}, {pixel.y}) · {pixel.value ?? 'missing'} {pixel.unit} · {pixel.wavelength_um?.toFixed(4) ?? '—'} μm · Flags: {pixel.flags.join(', ') || (pixel.covered ? 'none set' : 'no coverage')} · {pixel.reason}</p>}
      {spectrum && <>
        <p>Preliminary aperture spectrum, visit {spectrum.parameters.visit}. Radius 2 px; background annulus 3–5 px; fixed sky aperture. Flux in Jy; wavelength in μm.</p>
        {points.length ? <svg viewBox="0 0 650 220" role="img" aria-label="Preliminary aperture measurements and diagonal uncertainty in Jy" style={{maxWidth:650,width:'100%',background:'#151021'}}>
          <path d="M45 20V185H610" fill="none" stroke="#aaa"/>
          {points.map((p,i) => <g key={i} stroke="#c8aaff"><line x1={sx(p.wavelength_um)} x2={sx(p.wavelength_um)} y1={sy(p.flux-p.uncertainty)} y2={sy(p.flux+p.uncertainty)}/><circle cx={sx(p.wavelength_um)} cy={sy(p.flux)} r="3" fill="#c8aaff"><title>{p.wavelength_um} μm: {p.flux} ± {p.uncertainty} Jy; {p.time_utc}</title></circle></g>)}
          <text x="50" y="210" fill="white">{lo.toFixed(3)}–{hi.toFixed(3)} μm</text><text x="50" y="16" fill="white">{bottom.toPrecision(3)}–{top.toPrecision(3)} Jy</text>
        </svg> : <p>No exposure meets aperture coverage and background requirements at this position.</p>}
        <p>{spectrum.limitations}</p>
        <p><a href={download}>Export JSON with provenance</a> · <a href={download + '&format=csv'}>Export CSV</a></p>
      </>}
    </>}
  </details>;
}
