import './Spectrum.css';
const EPOCH_COLORS = ['#b48cff', '#5fd1c3', '#ffb35c', '#ff7aa8', '#8fc3ff', '#d6e36a', '#ff8f6b', '#9fe3b4'];

export default function SpectrumView({ spectrum, name }) {
  if (!spectrum) return <div className="empty progress"><b>Measuring the target in all six detectors</b><small>Available detector products are reused; archive loading can take several minutes.</small></div>;
  if (spectrum.error) return <div className="empty">{spectrum.error}</div>;
  const points = (spectrum.points || []).filter(p => Number.isFinite(p.flux_ujy) && Number.isFinite(p.wavelength_um));
  const done = spectrum.detectors_done?.length || 0;
  const status = spectrum.status === 'running' ? `Measuring detectors: ${done} of 6 done${spectrum.detectors_pending?.length ? ` (next: ${spectrum.detectors_pending.join(', ')})` : ''}` : `${done} of 6 detectors measured · ${points.length} points`;
  if (!points.length) return <div className="empty progress"><b>{status}</b><small>{spectrum.status === 'running' ? 'Points appear as each detector finishes.' : 'No usable aperture measurements; check coverage, saturation and detector errors.'}</small></div>;
  const W = 680, H = 400, L = 64, R = 16, T = 20, B = 46;
  const fluxes = points.flatMap(p => [p.flux_ujy - (p.err_ujy || 0), p.flux_ujy + (p.err_ujy || 0)]).sort((x, y) => x - y);
  const q = f => fluxes[Math.min(fluxes.length - 1, Math.max(0, Math.round(f * (fluxes.length - 1))))];
  let lo = Math.min(0, q(0)), hi = q(1);
  if (hi <= lo) hi = lo + 1;
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const x = w => L + (w - 0.7) / (5.1 - 0.7) * (W - L - R);
  const y = f => T + (1 - (Math.min(hi, Math.max(lo, f)) - lo) / (hi - lo)) * (H - T - B);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + (hi - lo) * i / 4);
  const epochs = [...new Set(points.map(p => p.epoch ?? 0))].sort((a, b) => a - b);
  const firstDate = e => points.filter(p => (p.epoch ?? 0) === e).map(p => p.time_utc).sort()[0]?.slice(0, 7);
  return <figure className="spectrum">
    <figcaption><b>{name}</b> · quick-look spectrum <small>{status}</small></figcaption>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Spectrum of ${name}: flux against wavelength`}>
      {ticks.map(t => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="grid"/><text x={L - 8} y={y(t) + 4} textAnchor="end">{Math.abs(t) >= 1000 ? `${(t / 1000).toFixed(1)}k` : t.toFixed(t < 10 ? 1 : 0)}</text></g>)}
      {[1, 2, 3, 4, 5].map(w => <g key={w}><line x1={x(w)} x2={x(w)} y1={H - B} y2={H - B + 5} className="axis"/><text x={x(w)} y={H - B + 19} textAnchor="middle">{w}</text></g>)}
      <line x1={L} x2={W - R} y1={H - B} y2={H - B} className="axis"/>
      <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" className="label">Wavelength (μm)</text>
      <text x={14} y={(T + H - B) / 2} textAnchor="middle" className="label" transform={`rotate(-90 14 ${(T + H - B) / 2})`}>Flux (μJy)</text>
      {points.map((p, i) => { const c = EPOCH_COLORS[(p.epoch ?? 0) % EPOCH_COLORS.length]; return <g key={i}>
        {p.err_ujy > 0 && <line x1={x(p.wavelength_um)} x2={x(p.wavelength_um)} y1={y(p.flux_ujy - p.err_ujy)} y2={y(p.flux_ujy + p.err_ujy)} stroke={c} strokeOpacity="0.45"/>}
        <circle cx={x(p.wavelength_um)} cy={y(p.flux_ujy)} r="3.2" fill={p.saturated ? 'none' : c} stroke={c}><title>{`${p.detector} · ${p.wavelength_um.toFixed(3)} μm · ${p.flux_ujy.toFixed(1)} μJy · ${p.time_utc.slice(0, 10)}${p.saturated ? ' · saturated (lower limit)' : ''}`}</title></circle>
      </g>; })}
    </svg>
    <div className="spectrum-legend">{epochs.map(e => <span key={e}><i style={{ background: EPOCH_COLORS[e % EPOCH_COLORS.length] }}/>{firstDate(e)}</span>)}</div>
    <p className="muted">{spectrum.note}</p>
  </figure>;
}

