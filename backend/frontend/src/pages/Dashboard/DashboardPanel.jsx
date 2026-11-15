/**
 * Shared Overview and Settings accordions shown above every dashboard view.
 *
 * - Overview: displays detailed photo metadata & contamination/instrument info
 *             that does not belong on the clean main media view.
 * - Settings: additional input fields for Side-by-Side Epoch Comparison
 *             (labels/dates), FOV, Detector Array, Player FPS, and target presets.
 */
import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { DEFAULT_FILTER, DEFAULT_SETTINGS } from '../../services/observationApi';
import { ROUTES } from '../../router/routes';

const TARGET_PRESETS = [
 {label: "Barnard's Star", coords: "Barnard's star"},
 {label: 'WISE 0855', coords: 'WISE J085510.83-071442.5'},
 {label: 'Epsilon Indi B', coords: 'eps Ind B'},
 {label: 'RW Aurigae', coords: 'RW Aur'},
 {label: 'R Draconis', coords: 'R Dra'},
];

const VISIT_COLOURS = ['#b795ff', '#56d6c9', '#ffb45d', '#ff7395', '#79b7ff', '#d7e875'];

function SpectrumPlot({ data }) {
  const points = (data?.points || []).filter(point =>
    Number.isFinite(Number(point.wavelength_um)) && Number.isFinite(Number(point.flux)));
  if (points.length === 0) return <p className="text-small text-muted">No unsaturated target measurements are available in the prepared arrays, so there are no spectrum points to plot.</p>;
  if (points.length < 2) return <p className="text-small text-muted">Only one unsaturated measurement is available; at least two are needed for a spectrum.</p>;

  const visits = new Map();
  points.forEach(point => {
    const visit = point.visit ?? 0;
    if (!visits.has(visit)) visits.set(visit, []);
    visits.get(visit).push(point);
  });
  const groups = [...visits.entries()].sort(([a], [b]) => Number(a) - Number(b));
  const wavelengths = points.map(point => Number(point.wavelength_um));
  const fluxes = points.map(point => Number(point.flux));
  const xMin = Math.min(...wavelengths);
  const xMax = Math.max(...wavelengths);
  const yMin = Math.min(0, ...fluxes);
  const yMax = Math.max(...fluxes);
  const x0 = 64, y0 = 20, width = 660, height = 205;
  const x = value => x0 + (Number(value) - xMin) / Math.max(xMax - xMin, 1e-8) * width;
  const y = value => y0 + height - (Number(value) - yMin) / Math.max(yMax - yMin, 1e-8) * height;
  const dates = entries => entries.map(point => point.time_utc).filter(Boolean).sort();

  return (
    <div className="spectrum-plot">
      <svg viewBox="0 0 760 280" role="img" aria-label="Exploratory aperture flux versus wavelength, coloured by visit">
        {Array.from({ length: 5 }, (_, index) => {
          const value = yMin + (yMax - yMin) * index / 4;
          const position = y(value);
          return <g key={`y-${index}`}>
            <line x1={x0} x2={x0 + width} y1={position} y2={position} className="spectrum-plot__grid" />
            <text x={x0 - 9} y={position + 4} textAnchor="end" className="spectrum-plot__tick">{Number(value.toPrecision(3)).toLocaleString()}</text>
          </g>;
        })}
        {Array.from({ length: 5 }, (_, index) => {
          const value = xMin + (xMax - xMin) * index / 4;
          const position = x(value);
          return <g key={`x-${index}`}>
            <line x1={position} x2={position} y1={y0} y2={y0 + height} className="spectrum-plot__grid" />
            <text x={position} y={y0 + height + 19} textAnchor="middle" className="spectrum-plot__tick">{value.toFixed(2)}</text>
          </g>;
        })}
        <line x1={x0} x2={x0 + width} y1={y0 + height} y2={y0 + height} className="spectrum-plot__axis" />
        <line x1={x0} x2={x0} y1={y0} y2={y0 + height} className="spectrum-plot__axis" />
        <text x={x0 + width / 2} y="274" textAnchor="middle" className="spectrum-plot__label">Wavelength (μm)</text>
        <text x="16" y={y0 + height / 2} textAnchor="middle" className="spectrum-plot__label" transform={`rotate(-90 16 ${y0 + height / 2})`}>Aperture flux</text>
        {groups.map(([visit, measurements], groupIndex) => measurements.map((point, pointIndex) => {
          const px = x(point.wavelength_um);
          const py = y(point.flux);
          const error = Number(point.error);
          const colour = VISIT_COLOURS[groupIndex % VISIT_COLOURS.length];
          const tooltip = `Visit ${Number(visit) + 1} · ${point.time_utc || 'time unavailable'} · ${point.detector || 'detector'} · ${Number(point.wavelength_um).toFixed(4)} μm · flux ${Number(point.flux).toPrecision(4)}${Number.isFinite(error) ? ` ± ${error.toPrecision(3)}` : ''}`;
          return <g key={`${visit}-${point.detector}-${point.time_utc}-${pointIndex}`}>
            <title>{tooltip}</title>
            {Number.isFinite(error) && <line x1={px} x2={px} y1={y(point.flux - error)} y2={y(point.flux + error)} stroke={colour} strokeOpacity="0.55" />}
            <circle cx={px} cy={py} r="3.1" fill={colour} fillOpacity="0.82" />
          </g>;
        }))}
      </svg>
      <ul className="spectrum-plot__legend" aria-label="Visits">
        {groups.map(([visit, measurements], index) => {
          const firstDate = dates(measurements)[0]?.slice(0, 10);
          return <li key={visit}>
            <span className="spectrum-plot__swatch" style={{ backgroundColor: VISIT_COLOURS[index % VISIT_COLOURS.length] }} />
            <span>Visit {Number(visit) + 1}{firstDate ? ` · ${firstDate}` : ''}</span>
          </li>;
        })}
      </ul>
    </div>
  );
}

export default function DashboardPanel({
  observation,
  filterConfig,
  onApplyFilter,
  settingsConfig,
  onApplySettings,
  onSelectCoordinates,
}) {
  const location = useLocation();
  const [draftFilter, setDraftFilter] = useState(filterConfig);
  const [draftSettings, setDraftSettings] = useState(settingsConfig);
  const [spectrumData, setSpectrumData] = useState(null);
  const [spectrumStatus, setSpectrumStatus] = useState('loading');

  useEffect(() => {
    setDraftFilter(filterConfig);
  }, [filterConfig]);

  useEffect(() => {
    setDraftSettings(settingsConfig);
  }, [settingsConfig]);

  useEffect(() => {
    const endpoint = observation.science?.spectrumUrl;
    if (!endpoint) { setSpectrumData(null); setSpectrumStatus('unavailable'); return undefined; }
    let cancelled = false;
    setSpectrumData(null);
    setSpectrumStatus('loading');
    fetch(endpoint).then(response => response.ok ? response.json() : null)
      .then(data => {
        if (!cancelled) {
          setSpectrumData(data);
          setSpectrumStatus(data ? 'ready' : 'unavailable');
        }
      }).catch(() => {
        if (!cancelled) { setSpectrumData(null); setSpectrumStatus('unavailable'); }
      });
    return () => { cancelled = true; };
  }, [observation.science?.spectrumUrl]);

  // Apply filter changes immediately so the ON/OFF state is always live everywhere.
  const updateFilter = (patch) => {
    setDraftFilter((prev) => {
      const next = { ...prev, ...patch };
      onApplyFilter(next);
      return next;
    });
  };

  return (
    <div className="workspace-accordions" aria-label="View information and settings">
      <details className="workspace-accordion">
        <summary className="workspace-accordion__summary">
          <span className="workspace-accordion__title">Overview</span>
          <span className="workspace-accordion__hint">Metadata &amp; science products</span>
          <span className="workspace-accordion__chevron" aria-hidden="true" />
        </summary>
        <section className="workspace-accordion__content panel" aria-label="Overview">
        <div className="inspector__body">
          <div className="meta-grid">
            {Object.entries(observation.metadata || {}).map(([key, value]) => (
              <div key={key} className="meta-card">
                <span className="text-caption text-muted">{key}</span>
                <span className="text-mono meta-card__value">{String(value)}</span>
              </div>
            ))}
            {observation.updatedAt && (
              <div className="meta-card">
                <span className="text-caption text-muted">Last Sync</span>
                <span className="text-mono meta-card__value">
                  {new Date(observation.updatedAt).toLocaleTimeString()}
                </span>
              </div>
            )}
            {observation.science && <>
              <div className="meta-card">
                <span className="text-caption text-muted">Visit quality</span>
                <span className="text-mono meta-card__value">{observation.science.quality.map(v => `${v.index + 1}: ${v.level}`).join(' · ') || '—'}</span>
              </div>
              <div className="meta-card">
                <span className="text-caption text-muted">Matched comparison</span>
                <span className="text-mono meta-card__value">{observation.science.sharedWavelength ? `${observation.science.sharedWavelength.min.toFixed(3)}–${observation.science.sharedWavelength.max.toFixed(3)} μm` : 'No shared range'}</span>
              </div>
              <div className="meta-card meta-card--wide science-products">
                <div className="science-products__header">
                  <div>
                    <span className="text-caption text-muted">On-the-fly spectrum</span>
                    <p className="science-products__title">Aperture flux by wavelength</p>
                  </div>
                  <span className="science-products__badge">Exploratory</span>
                </div>
                {spectrumStatus === 'loading' ? <p className="text-small text-muted">Loading measurements…</p>
                  : spectrumStatus === 'ready' ? <SpectrumPlot data={spectrumData} />
                    : <p className="text-small text-muted">Spectrum data could not be loaded for this observation.</p>}
                <p className="text-caption text-muted">Arrays: {spectrumData?.detectors?.join(' · ') || '—'}. Simple aperture flux with variance-based errors; not calibrated flux. Points at saturated targets are omitted.</p>
                <div className="science-products__actions">
                  {observation.science.colourUrl ? (
                    location.pathname === ROUTES.colour
                      ? <span className="text-small text-muted">Colour composite is open in this view.</span>
                      : <Link className="btn-ghost text-label" to={{ pathname: ROUTES.colour, search: location.search }}>Open colour composite</Link>
                  ) : <span className="text-small text-muted">Prepare all six arrays in Settings to create the colour composite.</span>}
                </div>
              </div>
              {observation.science.epsilonPanel && <div className="meta-card meta-card--wide"><span className="text-caption text-muted">Epsilon Indi B science</span><span className="meta-card__value"><a href={observation.science.epsilonPanel.summaryUrl} target="_blank" rel="noreferrer">comparison report</a>{' · '}<a href={observation.science.epsilonPanel.motionUrl} target="_blank" rel="noreferrer">motion measurement</a></span></div>}
            </>}
          </div>
        </div>
        </section>
      </details>

      <details className="workspace-accordion">
        <summary className="workspace-accordion__summary">
          <span className="workspace-accordion__title">Settings</span>
          <span className="workspace-accordion__hint">Detectors, display &amp; comparison</span>
          <span className="workspace-accordion__chevron" aria-hidden="true" />
        </summary>
        <section className="workspace-accordion__content panel" aria-label="Settings">
        <form
          className="inspector__body inspector__form"
          onSubmit={(e) => {
            e.preventDefault();
            onApplySettings(draftSettings);
          }}
        >
          <p className="text-label text-muted">Available observations (blank = first / last)</p>
          <div className="form-grid">
            <label className="field">
              <span className="text-caption text-muted">Epoch 1 Label</span>
              <input
                type="text"
                className="field__control text-small"
                value={draftSettings.epoch1Label}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, epoch1Label: e.target.value }))}
              />
            </label>

            <label className="field">
              <span className="text-caption text-muted">Epoch 1 Date</span>
              <select className="field__control text-mono" value={draftSettings.epoch1Date} onChange={e => setDraftSettings(prev => ({...prev, epoch1Date:e.target.value}))}>
<option value="">First available observation</option>
{(observation.compare?.availableEpochs || []).map(date => <option key={date} value={date}>{date} UTC</option>)}
</select>
            </label>

            <label className="field">
              <span className="text-caption text-muted">Epoch 2 Label</span>
              <input
                type="text"
                className="field__control text-small"
                value={draftSettings.epoch2Label}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, epoch2Label: e.target.value }))}
              />
            </label>

            <label className="field">
              <span className="text-caption text-muted">Epoch 2 Date</span>
              <select className="field__control text-mono" value={draftSettings.epoch2Date} onChange={e => setDraftSettings(prev => ({...prev, epoch2Date:e.target.value}))}>
<option value="">Last available observation</option>
{(observation.compare?.availableEpochs || []).map(date => <option key={date} value={date}>{date} UTC</option>)}
</select>
            </label>
            <label className="field checkbox-field"><span className="text-caption text-muted">Quality mode</span><span><input type="checkbox" checked={Boolean(draftSettings.cleanMask)} onChange={e => setDraftSettings(prev => ({ ...prev, cleanMask: e.target.checked }))} /> Pro artifact mask</span></label>
            <label className="field checkbox-field"><span className="text-caption text-muted">Display interpolation</span><span><input type="checkbox" checked={draftSettings.smoothDisplay !== false} onChange={e => setDraftSettings(prev => ({ ...prev, smoothDisplay: e.target.checked }))} /> Bilinear smoothing</span></label>
            <label className="field checkbox-field"><span className="text-caption text-muted">Background</span><span><input type="checkbox" checked={Boolean(draftFilter.enabled)} onChange={e => updateFilter({ enabled: e.target.checked })} /> Subtract supplied ZODI model</span></label>
          </div>

          <p className="text-label text-muted">Instrument &amp; Player Inputs</p>
          <div className="form-grid">
            <label className="field">
              <span className="text-caption text-muted">Field of View (3, 6 or 12 arcmin)</span>
              <select className="field__control text-mono" value={draftSettings.fovArcmin}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, fovArcmin: e.target.value }))}>
                {[3,6,12].map(value => <option key={value} value={String(value)}>{value} arcmin</option>)}
              </select>
            </label>

            <label className="field">
              <span className="text-caption text-muted">Detector Array</span>
              <select
                className="field__control text-small"
                value={draftSettings.detectorArray}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, detectorArray: e.target.value }))}
              >
                
                <option value="1">Array 1 (0.75–1.1 μm)</option>
                <option value="2">Array 2 (1.1–1.6 μm)</option>
                <option value="3">Array 3 (1.6–2.4 μm)</option>
                <option value="4">Array 4 (2.4–3.8 μm)</option>
                <option value="5">Array 5 (3.8–4.4 μm)</option>
                <option value="6">Array 6 (4.4–5.0 μm)</option>
                <option value="all">All six arrays (colour composite)</option>
              </select>
            </label>

            <label className="field">
              <span className="text-caption text-muted">Sequence FPS</span>
              <input
                type="number"
                min={1}
                max={24}
                className="field__control text-mono"
                value={draftSettings.playerFps}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, playerFps: Number(e.target.value) || 3 }))}
              />
            </label>
          </div>

          <div className="presets">
            <span className="text-caption text-muted">Quick Challenge Targets:</span>
            <div className="presets__list">
              {TARGET_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="preset-chip text-caption"
                  onClick={() => onSelectCoordinates(preset.coords)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div className="inspector__actions">
            <button type="submit" className="btn-primary text-label">
              Apply Settings
            </button>
            <button
              type="button"
              className="btn-ghost text-label"
              onClick={() => {
                setDraftSettings(DEFAULT_SETTINGS);
                onApplySettings(DEFAULT_SETTINGS);
              }}
            >
              Reset Defaults
            </button>
          </div>
        </form>
        </section>
      </details>
    </div>
  );
}

