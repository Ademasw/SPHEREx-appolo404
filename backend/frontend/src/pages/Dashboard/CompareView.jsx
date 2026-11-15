import { useEffect, useState } from 'react';
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
  const endpoint = observation.science?.matchedRequestUrl;
  const [matched, setMatched] = useState(null);
  const [matchError, setMatchError] = useState('');
  const [matching, setMatching] = useState(false);
  useEffect(() => {setMatched(null);setMatchError('');setMatching(false);}, [endpoint]);
  useEffect(() => {
    if (!matching || !endpoint) return;
    const controller = new AbortController();
    fetch(endpoint,{signal:controller.signal}).then(async response => {
      const data=await response.json(); if (!response.ok) throw new Error(data.detail || 'Comparison unavailable'); return data;
    }).then(data => {if (!controller.signal.aborted) setMatched(data);}).catch(error => {if(error.name !== 'AbortError') setMatchError(error.message);}).finally(() => {if(!controller.signal.aborted)setMatching(false);});
    return () => controller.abort();
  }, [matching,endpoint]);

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
      <div className="panel" style={{padding:20}}>
        <p>Broadband visits above can contain different wavelengths. Spectral comparison selects compatible measurements at each pixel.</p>
        <button disabled={!endpoint || matching || status !== 'ready'} onClick={() => {setMatchError('');setMatching(true);}}>Compare compatible wavelengths</button>
        {!endpoint && status === 'ready' && <p>Choose two different available visits from the same detector.</p>}
        {matching && <p>Checking local passbands…</p>}
        {matchError && <p role="alert">{matchError}</p>}
        {matched && <>
          <img style={{maxWidth:'100%'}} src={new URL(matched.difference_url,new URL(endpoint,window.location.href)).href} alt="Compatible B minus A; white brighter, black fainter"/>
          <p>B − A: white means brighter in B; black means fainter. Compatible coverage: {(matched.usable_grid_fraction*100).toFixed(1)}%.</p>
          <p>{matched.limitations}</p>
          <a href={new URL(matched.fits_url,new URL(endpoint,window.location.href)).href}>Export difference, mask and contributions (FITS)</a>
        </>}
      </div>
    </section>
  );
}
