import SpectrumGenerator from '../../components/spectrum/SpectrumGenerator.jsx';
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
  useEffect(() => {
    setDraftFilter(filterConfig);
  }, [filterConfig]);

  useEffect(() => {
    setDraftSettings(settingsConfig);
  }, [settingsConfig]);

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
                <SpectrumGenerator name={observation.coordinates} query={{q:observation.coordinates,fov:Number(settingsConfig.fovArcmin)/60,bg:filterConfig.background || (filterConfig.enabled ? 'model' : 'none'),clean:settingsConfig.cleanMask,smooth:settingsConfig.smoothDisplay}}/>
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

          {draftSettings.detectorArray === 'all' && <label className="field">Displayed detector (Player and Compare)
            <select value={draftSettings.displayDetector || '1'} onChange={e => setDraftSettings(prev => ({...prev,displayDetector:e.target.value}))}>
              {['0.75–1.1','1.1–1.6','1.6–2.4','2.4–3.8','3.8–4.4','4.4–5.0'].map((band,i) => <option key={i} value={String(i+1)}>D{i+1} · {band} μm</option>)}
            </select></label>}
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

