/**
 * DashboardPanel — functional workspace panel driven by the Sidebar menu
 * (`Overview`, `Filter`, `Settings`).
 *
 * - Overview: displays detailed photo metadata & contamination/instrument info
 *             that does not belong on the clean main media view.
 * - Filter:   configures Zodiacal Light Subtraction ("Zodi Subtraction") and
 *             pushes the filter parameters to the backend query.
 * - Settings: additional input fields for Side-by-Side Epoch Comparison
 *             (labels/dates), FOV, Detector Array, Player FPS, and target presets.
 */
import { useEffect, useState } from 'react';
import { DEFAULT_FILTER, DEFAULT_SETTINGS } from '../../services/observationApi';

const TARGET_PRESETS = [
  { label: "Barnard's Star", coords: '269.452, 4.693' },
  { label: 'WISE 0855', coords: '133.795, -7.245' },
  { label: 'Epsilon Indi B', coords: '330.840, -56.786' },
  { label: 'RW Aurigae', coords: '76.956, 30.401' },
  { label: 'R Draconis', coords: '248.163, 66.755' },
];

export default function DashboardPanel({
  activeMenu,
  onClose,
  observation,
  filterConfig,
  onApplyFilter,
  settingsConfig,
  onApplySettings,
  onSelectCoordinates,
}) {
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

  if (!activeMenu) return null;

  return (
    <section className="inspector panel" aria-label={`${activeMenu} panel`}>
      <header className="inspector__header">
        <div>
          <p className="text-label text-accent">
            {activeMenu === 'overview' && 'Photo & Telemetry Metadata'}
            {activeMenu === 'filter' && 'Background Processing'}
            {activeMenu === 'settings' && 'Comparison & Query Parameters'}
          </p>
          <h2 className="text-h2">
            {activeMenu === 'overview' && 'Overview'}
            {activeMenu === 'filter' && 'Filter · Zodi Subtraction'}
            {activeMenu === 'settings' && 'Settings'}
          </h2>
        </div>

        <button type="button" className="inspector__close text-label" onClick={onClose} aria-label="Collapse panel">
          Hide ×
        </button>
      </header>

      {/* ------------------------- 1. OVERVIEW ------------------------- */}
      {activeMenu === 'overview' && (
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
          </div>
        </div>
      )}

      {/* -------------------------- 2. FILTER -------------------------- */}
      {activeMenu === 'filter' && (
        <form
          className="inspector__body inspector__form"
          onSubmit={(e) => {
            e.preventDefault();
            onApplyFilter(draftFilter);
          }}
        >
          <div className="form-grid">
            <label className={`toggle-field${draftFilter.enabled ? ' is-on' : ' is-off'}`}>
              <span className="toggle-field__copy">
                <span className="text-small">
                  Zodiacal Light Subtraction (Zodi) ·{' '}
                  <strong className={draftFilter.enabled ? 'text-accent' : 'text-muted'}>
                    {draftFilter.enabled ? 'ON' : 'OFF'}
                  </strong>
                </span>
                <span className="text-caption text-muted">
                  Removes foreground interplanetary dust glow to reveal faint moving objects.
                </span>
              </span>
              <input
                type="checkbox"
                checked={draftFilter.enabled}
                onChange={(e) => updateFilter({ enabled: e.target.checked })}
              />
            </label>

            <label className="field">
              <span className="text-label text-muted">Subtraction Model</span>
              <select
                className="field__control text-small"
                value={draftFilter.model}
                disabled={!draftFilter.enabled}
                onChange={(e) => updateFilter({ model: e.target.value })}
              >
                <option value="kelsall">Kelsall DIRBE Model</option>
                <option value="spherex">SPHEREx Spectral Sky Fit</option>
                <option value="median">Local Sky Median</option>
              </select>
            </label>

            <label className="field">
              <span className="text-label text-muted">
                Subtraction Strength · <span className="text-mono">{draftFilter.strength}%</span>
              </span>
              <input
                type="range"
                min={0}
                max={150}
                step={5}
                disabled={!draftFilter.enabled}
                value={draftFilter.strength}
                onChange={(e) => updateFilter({ strength: Number(e.target.value) })}
                className="field__range"
              />
            </label>

            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={draftFilter.maskSaturated}
                onChange={(e) => updateFilter({ maskSaturated: e.target.checked })}
              />
              <span className="text-small">Mask saturated foreground stars</span>
            </label>
          </div>

          <div className="inspector__actions">
            <button
              type="button"
              className="btn-primary text-label"
              onClick={() => updateFilter({ enabled: !draftFilter.enabled })}
            >
              {draftFilter.enabled ? 'Disable Zodi Filter' : 'Enable Zodi Filter'}
            </button>
            <button
              type="button"
              className="btn-ghost text-label"
              onClick={() => {
                setDraftFilter(DEFAULT_FILTER);
                onApplyFilter(DEFAULT_FILTER);
              }}
            >
              Reset
            </button>
          </div>
        </form>
      )}

      {/* ------------------------- 3. SETTINGS ------------------------- */}
      {activeMenu === 'settings' && (
        <form
          className="inspector__body inspector__form"
          onSubmit={(e) => {
            e.preventDefault();
            onApplySettings(draftSettings);
          }}
        >
          <p className="text-label text-muted">Side-by-Side Epoch Comparison Inputs</p>
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
              <input
                type="date"
                className="field__control text-mono"
                value={draftSettings.epoch1Date}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, epoch1Date: e.target.value }))}
              />
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
              <input
                type="date"
                className="field__control text-mono"
                value={draftSettings.epoch2Date}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, epoch2Date: e.target.value }))}
              />
            </label>
          </div>

          <p className="text-label text-muted">Instrument &amp; Player Inputs</p>
          <div className="form-grid">
            <label className="field">
              <span className="text-caption text-muted">Field of View (arcmin)</span>
              <input
                type="number"
                min={1}
                max={60}
                className="field__control text-mono"
                value={draftSettings.fovArcmin}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, fovArcmin: e.target.value }))}
              />
            </label>

            <label className="field">
              <span className="text-caption text-muted">Detector Array</span>
              <select
                className="field__control text-small"
                value={draftSettings.detectorArray}
                onChange={(e) => setDraftSettings((prev) => ({ ...prev, detectorArray: e.target.value }))}
              >
                <option value="all">All 6 Arrays (0.75–5.0 μm)</option>
                <option value="1">Array 1 (0.75–1.11 μm)</option>
                <option value="2">Array 2 (1.11–1.64 μm)</option>
                <option value="3">Array 3 (1.64–2.42 μm)</option>
                <option value="4">Array 4 (2.42–3.13 μm)</option>
                <option value="5">Array 5 (3.13–3.83 μm)</option>
                <option value="6">Array 6 (3.83–5.00 μm)</option>
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
      )}
    </section>
  );
}

