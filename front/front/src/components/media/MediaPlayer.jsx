/**
 * MediaPlayer — large media container ready for local placeholders OR backend streams.
 *
 * Three supported media modes (determined automatically by props):
 *   1. VIDEO (`videoSrc` = URL of .mp4 / .webm / stream) -> custom-controlled <video>
 *   2. LIVE / GIF STREAM (`streamSrc` = GIF, MJPEG, or backend-pushed image URL) -> <img>
 *   3. IMAGE SEQUENCE (`frames` = array of image URLs) -> default, stepped by timer
 *      at `fps || PLAYER.framesPerSecond` × chosen speed multiplier.
 *
 * Also accepts `isLoading` and `error` props so the stage renders clean overlays
 * while the backend fetches or streams new observations.
 *
 * Keyboard: when the player has focus, Space = play/pause, ←/→ = step.
 */
import { useEffect, useRef, useState } from 'react';
import { PLAYER } from '../../config/animation';
import './MediaPlayer.css';

const formatTime = (s) => {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
};

export default function MediaPlayer({
  frames = [],
  videoSrc = null,
  streamSrc = null,
  fps = null,
  isLoading = false,
  error = null,
  alt = 'Observation sequence',
}) {
  const isVideo = Boolean(videoSrc);
  const isStream = !isVideo && Boolean(streamSrc);
  const videoRef = useRef(null);

  const [isPlaying, setIsPlaying] = useState(PLAYER.autoplay);
  const [speed, setSpeed] = useState(1);
  const [frameIndex, setFrameIndex] = useState(0);
  const [videoTime, setVideoTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);

  const frameCount = frames.length;
  const effectiveFps = fps || PLAYER.framesPerSecond;

  // Reset to the first frame whenever the backend delivers a new sequence.
  useEffect(() => {
    setFrameIndex(0);
  }, [frames]);

  // Preload all frames so playback never flickers.
  useEffect(() => {
    if (isVideo || isStream) return;
    frames.forEach((src) => {
      const img = new Image();
      img.src = src;
    });
  }, [frames, isVideo, isStream]);

  // IMAGE-SEQUENCE playback loop.
  useEffect(() => {
    if (isVideo || isStream || !isPlaying || frameCount < 2) return undefined;
    const intervalMs = 1000 / (effectiveFps * speed);
    const id = setInterval(() => setFrameIndex((i) => (i + 1) % frameCount), intervalMs);
    return () => clearInterval(id);
  }, [isVideo, isStream, isPlaying, frameCount, effectiveFps, speed]);

  // VIDEO playback sync.
  useEffect(() => {
    const video = videoRef.current;
    if (!isVideo || !video) return;
    video.playbackRate = speed;
    if (isPlaying) video.play().catch(() => setIsPlaying(false));
    else video.pause();
  }, [isVideo, isPlaying, speed]);

  const togglePlay = () => {
    if (isStream) return;
    setIsPlaying((p) => !p);
  };

  const seek = (value) => {
    if (isVideo) {
      if (videoRef.current) videoRef.current.currentTime = value;
      setVideoTime(value);
    } else if (!isStream) {
      setFrameIndex(value);
    }
  };

  const step = (delta) => {
    if (isStream) return;
    setIsPlaying(false);
    if (isVideo) seek(Math.min(videoDuration, Math.max(0, videoTime + delta * 0.5)));
    else if (frameCount > 0) setFrameIndex((i) => (i + delta + frameCount) % frameCount);
  };

  const onKeyDown = (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.code === 'Space') {
      e.preventDefault();
      togglePlay();
    } else if (e.code === 'ArrowRight') step(1);
    else if (e.code === 'ArrowLeft') step(-1);
  };

  const sliderProps = isVideo
    ? { min: 0, max: videoDuration || 0, step: 0.01, value: videoTime }
    : { min: 0, max: Math.max(0, frameCount - 1), step: 1, value: frameIndex };

  const progress = sliderProps.max ? (sliderProps.value / sliderProps.max) * 100 : 0;

  return (
    <div className="player panel" tabIndex={0} onKeyDown={onKeyDown} aria-label="Media player">
      {/* ---- Media container (data-slot marks the backend broadcast target) ---- */}
      <div className="player__stage" data-slot="player-media" aria-busy={isLoading}>
        {isVideo ? (
          <video
            ref={videoRef}
            src={videoSrc}
            className="player__media"
            muted
            loop
            playsInline
            onLoadedMetadata={(e) => setVideoDuration(e.currentTarget.duration)}
            onTimeUpdate={(e) => setVideoTime(e.currentTarget.currentTime)}
          />
        ) : isStream ? (
          <img src={streamSrc} alt={alt} className="player__media" />
        ) : frameCount ? (
          <img src={frames[frameIndex]} alt={alt} className="player__media" />
        ) : (
          <p className="text-small text-muted">No media — waiting for backend stream or frames</p>
        )}

        {isLoading && (
          <div className="media-overlay">
            <span className="media-overlay__spinner" aria-hidden="true" />
            <span className="text-small">Receiving observation feed…</span>
          </div>
        )}

        {error && !isLoading && (
          <div className="media-overlay media-overlay--error" role="alert">
            <span className="text-small">{error}</span>
          </div>
        )}
      </div>

      {/* ---- Controls ---- */}
      <div className="player__controls">
        <button
          type="button"
          className="player__btn"
          onClick={() => step(-1)}
          disabled={isStream}
          aria-label="Previous"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 5h2v14H6zM20 5v14L9 12z" />
          </svg>
        </button>

        <button
          type="button"
          className="player__btn player__btn--main"
          onClick={togglePlay}
          disabled={isStream}
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying && !isStream ? (
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M7 4v16l13-8z" />
            </svg>
          )}
        </button>

        <button
          type="button"
          className="player__btn"
          onClick={() => step(1)}
          disabled={isStream}
          aria-label="Next"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M16 5h2v14h-2zM4 5v14l11-7z" />
          </svg>
        </button>

        <input
          type="range"
          className="player__timeline"
          aria-label="Timeline"
          disabled={isStream}
          {...sliderProps}
          style={{ '--progress': `${isStream ? 100 : progress}%` }}
          onChange={(e) => {
            setIsPlaying(false);
            seek(Number(e.target.value));
          }}
        />

        <span className="player__counter text-mono text-muted">
          {isStream
            ? 'LIVE FEED'
            : isVideo
              ? `${formatTime(videoTime)} / ${formatTime(videoDuration)}`
              : `${String(frameIndex + 1).padStart(2, '0')} / ${String(frameCount).padStart(2, '0')}`}
        </span>

        <div className="player__speeds" role="group" aria-label="Playback speed">
          {PLAYER.speeds.map((s) => (
            <button
              key={s}
              type="button"
              disabled={isStream}
              className={`player__speed text-mono${s === speed ? ' is-active' : ''}`}
              onClick={() => setSpeed(s)}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
