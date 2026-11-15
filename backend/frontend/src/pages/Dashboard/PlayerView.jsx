/**
 * PlayerView — View Mode A (Page 2): one large media container + playback controls.
 *
 * Receives `observation`, `status`, `error`, and `coordinates` from Dashboard's
 * Outlet context. Detailed photo metadata lives in the `Overview` menu panel
 * to keep the main viewing window focused on the sequence.
 */
import { useOutletContext } from 'react-router-dom';
import MediaPlayer from '../../components/media/MediaPlayer.jsx';

const STATUS_LABELS = {
  idle: 'Enter a target',
  placeholder: 'No observation',
  loading: 'Syncing backend…',
  ready: 'Backend ready',
  live: 'Live stream',
  error: 'Feed error',
};

export default function PlayerView() {
  const { coordinates, observation, status, error } = useOutletContext();
  const { player } = observation;

  return (
    <section className="view">
      <header className="view__header">
        <div>
          <p className="text-label text-accent">View mode A</p>
          <h1 className="text-h1">Sequence Player</h1>
        </div>

        <div className="view__meta">


          <span className={`view__status view__status--${status} text-caption`}>
            <span className="view__status-dot" aria-hidden="true" />
            {STATUS_LABELS[status] || status}
          </span>

          <p className="view__target text-mono text-muted">Target: {coordinates || '— not set —'}</p>
        </div>
      </header>

      <MediaPlayer
        frames={player.frames}
        frameMetadata={player.frameMetadata}
        videoSrc={player.videoUrl}
        streamSrc={player.streamUrl}
        fps={player.fps}
        isLoading={status === 'loading'}
        error={error}
        alt={`SPHEREx observation sequence${coordinates ? ` at ${coordinates}` : ''}`}
      />
    </section>
  );
}
