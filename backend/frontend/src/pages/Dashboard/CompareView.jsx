/**
 * CompareView — View Mode B (Page 3): two epochs side-by-side.
 *
 * Receives `observation`, `status`, `error`, and `coordinates` from Dashboard's
 * Outlet context. Observation notes have been removed; detailed metadata lives
 * in the shared Overview and Settings accordions above the image panels.
 */
import { useOutletContext } from 'react-router-dom';

const STATUS_LABELS = {
  idle: 'Enter a target',
  placeholder: 'No observation',
  loading: 'Syncing backend…',
  ready: 'Backend ready',
  live: 'Live stream',
  error: 'Feed error',
};

export default function CompareView() {
  const { coordinates, observation, status, error } = useOutletContext();
  const { compare } = observation;

  return (
    <section className="view">
      <header className="view__header">
        <div>
          <p className="text-label text-accent">View mode B</p>
          <h1 className="text-h1">Epoch Comparison</h1>
        </div>

        <div className="view__meta">
          <span className={`view__status view__status--${status} text-caption`}>
            <span className="view__status-dot" aria-hidden="true" />
            {STATUS_LABELS[status] || status}
          </span>

          <p className="view__target text-mono text-muted">Target: {coordinates || '— not set —'}</p>
        </div>
      </header>

      <div className="compare">
        {compare.epochs.map((epoch, idx) => (
          <figure key={epoch.id || idx} className="compare__panel panel">
            <div
              className="compare__frame"
              data-slot={`epoch-${epoch.id || idx}`}
              aria-busy={status === 'loading'}
            >
              {epoch.imageUrl ? (
                <img src={epoch.imageUrl} alt={`${epoch.label} observation`} />
              ) : (
                <div className="compare__empty text-small text-muted">
                  Waiting for {epoch.label} image…
                </div>
              )}

              {status === 'loading' && (
                <div className="media-overlay">
                  <span className="media-overlay__spinner" aria-hidden="true" />
                  <span className="text-small">Loading {epoch.label}…</span>
                </div>
              )}

              {error && status !== 'loading' && (
                <div className="media-overlay media-overlay--error" role="alert">
                  <span className="text-small">{error}</span>
                </div>
              )}
            </div>
            <figcaption className="compare__caption">
              <div>
                <span className="text-h2">{epoch.label}</span>
                {epoch.meta && <span className="compare__meta text-caption text-muted">{epoch.meta}</span>}
              </div>
              <span className="text-mono text-muted">{epoch.date}</span>
            </figcaption>
          </figure>
        ))}
      </div>
      {observation.science?.sharedWavelength && <p className="text-small text-muted">Central wavelength overlap: {observation.science.sharedWavelength.min.toFixed(3)}–{observation.science.sharedWavelength.max.toFixed(3)} μm. This does not establish pixelwise spectral compatibility. {observation.science.matchedRequestUrl && <a href={observation.science.matchedRequestUrl} target="_blank" rel="noreferrer">Generate diagnostic difference for selected visits</a>}</p>}
    </section>
  );
}
