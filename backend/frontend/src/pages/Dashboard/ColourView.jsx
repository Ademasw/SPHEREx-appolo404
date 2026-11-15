import { useOutletContext } from 'react-router-dom';

export default function ColourView() {
  const { coordinates, observation, status, error } = useOutletContext();
  const key = observation.science?.sequenceKey;
  const imageUrl = observation.science?.colourUrl;
  const ready = status === 'ready' || status === 'live';

  return (
    <section className="view colour-view">
      <header className="view__header">
        <div>
          <p className="text-label text-accent">View mode C</p>
          <h1 className="text-h1">Infrared Colour Composite</h1>
        </div>
        <div className="view__meta">
          <span className={`view__status view__status--${status} text-caption`}>
            <span className="view__status-dot" aria-hidden="true" />{status}
          </span>
          <p className="view__target text-mono text-muted">Target: {coordinates || '— not set —'}</p>
        </div>
      </header>

      <div className="colour-view__frame panel" aria-busy={!ready}>
        {error && <p className="text-small text-muted">{error}</p>}
        {!error && ready && imageUrl && (
          <img src={`${imageUrl}?render=rgb2`} alt="SPHEREx infrared colour composite" />
        )}
        {!error && !ready && <p className="text-small text-muted">Preparing all six detector arrays…</p>}
        {!error && ready && !imageUrl && <p className="text-small text-muted">Colour mode needs all six detector arrays. Select “All six arrays” in Settings and apply.</p>}
      </div>
      <p className="text-small text-muted colour-view__legend">
        Blue = D1+D2 (0.75–1.62 μm) · Green = D3+D4 (1.62–3.82 μm) · Red = D5+D6 (3.83–5.0 μm).
        This is a display composite from matched visit stacks, not a calibrated RGB photograph.
      </p>
      {key && <p className="text-caption text-muted">Visits are paired by nearest observation date.</p>}
    </section>
  );
}
