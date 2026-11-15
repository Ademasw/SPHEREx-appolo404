/**
 * CelestialGlobe — Aladin-Lite-style interactive 3D celestial sphere window
 * wrapped in space photographs mapped from Earth observation coordinates.
 *
 * HOW IT WORKS
 *   - Fetches sky tiles from `fetchSkyGlobeTiles()` (`src/services/observationApi.js`).
 *     Until the backend is merged, it uses `DEFAULT_GLOBE_TILES` (placeholder
 *     space photographs from `src/assets/` mapped across the 3D sphere).
 *   - Projects each photograph onto a curved 3D spherical mesh (`subdivided`
 *     triangles warped via 2D affine canvas transforms) so the photos genuinely
 *     wrap around the rotating globe.
 *   - Supports drag-to-rotate, wheel/button zoom, auto-rotation, equatorial
 *     RA/Dec graticule grid, coordinate search, and tile click inspection.
 *   - Exposes `data-slot="aladin-globe-viewport"` so an external Aladin Lite
 *     instance (`A.aladin(...)`) or backend WebSocket/REST feed can also be
 *     mounted or merged without changing the surrounding UI.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  DEFAULT_GLOBE_TILES,
  fetchSkyGlobeTiles,
  isBackendConfigured,
} from '../../services/observationApi';
import { ROUTES } from '../../router/routes';
import './CelestialGlobe.css';

const DEG2RAD = Math.PI / 180;
const RAD2DEG = 180 / Math.PI;

const wrapDeg360 = (deg) => ((deg % 360) + 360) % 360;
const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

/** Format Right Ascension (degrees) as HHh MMm SSs, like Aladin Lite. */
function formatRA(deg) {
  const norm = wrapDeg360(deg);
  const totalHours = norm / 15;
  const h = Math.floor(totalHours);
  const m = Math.floor((totalHours - h) * 60);
  const s = (((totalHours - h) * 60 - m) * 60).toFixed(1);
  return `${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m ${String(s).padStart(4, '0')}s`;
}

/** Format Declination (degrees) as ±DD° MM′ SS″. */
function formatDec(deg) {
  const sign = deg >= 0 ? '+' : '−';
  const abs = Math.abs(clamp(deg, -90, 90));
  const d = Math.floor(abs);
  const m = Math.floor((abs - d) * 60);
  const s = Math.round(((abs - d) * 60 - m) * 60);
  return `${sign}${String(d).padStart(2, '0')}° ${String(m).padStart(2, '0')}′ ${String(s).padStart(2, '0')}″`;
}

/** Convert spherical (raDeg, decDeg) into a 3D unit vector on the sphere. */
function sphToVec(raDeg, decDeg) {
  const ra = raDeg * DEG2RAD;
  const dec = decDeg * DEG2RAD;
  const cosDec = Math.cos(dec);
  return [cosDec * Math.sin(ra), Math.sin(dec), cosDec * Math.cos(ra)];
}

/** Rotate a 3D point by camera yaw (centerRA) and pitch (centerDec). */
function rotateForCamera([x, y, z], centerRaDeg, centerDecDeg) {
  const yaw = -centerRaDeg * DEG2RAD;
  const pitch = centerDecDeg * DEG2RAD;

  // Yaw around Y axis
  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;

  // Pitch around X axis
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  const y2 = y * cp - z1 * sp;
  const z2 = y * sp + z1 * cp;

  return [x1, y2, z2];
}

/**
 * Draw a textured triangle `(u0,v0)-(u1,v1)-(u2,v2)` mapped to screen points
 * `(x0,y0)-(x1,y1)-(x2,y2)` using a 2D canvas affine transform.
 */
function drawTexturedTriangle(ctx, img, x0, y0, x1, y1, x2, y2, u0, v0, u1, v1, u2, v2) {
  const det = u0 * (v1 - v2) - v0 * (u1 - u2) + (u1 * v2 - u2 * v1);
  if (Math.abs(det) < 1e-5) return;

  const idet = 1 / det;
  const a = (x0 * (v1 - v2) - v0 * (x1 - x2) + (x1 * v2 - x2 * v1)) * idet;
  const b = (y0 * (v1 - v2) - v0 * (y1 - y2) + (y1 * v2 - y2 * v1)) * idet;
  const c = (u0 * (x1 - x2) - x0 * (u1 - u2) + (u1 * x2 - u2 * x1)) * idet;
  const d = (u0 * (y1 - y2) - y0 * (u1 - u2) + (u1 * y2 - u2 * y1)) * idet;
  const e =
    (u0 * (v1 * x2 - v2 * x1) - v0 * (u1 * x2 - u2 * x1) + x0 * (u1 * v2 - u2 * v1)) * idet;
  const f =
    (u0 * (v1 * y2 - v2 * y1) - v0 * (u1 * y2 - u2 * y1) + y0 * (u1 * v2 - u2 * v1)) * idet;

  ctx.save();
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.closePath();
  ctx.clip();
  ctx.transform(a, b, c, d, e, f);
  ctx.drawImage(img, 0, 0);
  ctx.restore();
}

export default function CelestialGlobe() {
  const navigate = useNavigate();
  const canvasRef = useRef(null);
  const imagesRef = useRef(new Map());

  const [tiles, setTiles] = useState(DEFAULT_GLOBE_TILES);
  const [selectedTileId, setSelectedTileId] = useState(DEFAULT_GLOBE_TILES[0].id);
  const [centerRa, setCenterRa] = useState(269.45);
  const [centerDec, setCenterDec] = useState(12.0);
  const [zoom, setZoom] = useState(1.0);
  const [autoSpin, setAutoSpin] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [surveyMode, setSurveyMode] = useState('mosaic'); // 'mosaic' | 'cutouts'
  const [searchInput, setSearchInput] = useState('');
  const [syncState, setSyncState] = useState(isBackendConfigured() ? 'loading' : 'placeholder');

  // Keep camera state in a ref for the 60fps requestAnimationFrame loop.
  const viewRef = useRef({
    ra: centerRa,
    dec: centerDec,
    targetRa: null,
    targetDec: null,
    zoom: 1.0,
    autoSpin: true,
    showGrid: true,
    surveyMode: 'mosaic',
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    dragMoved: false,
  });

  viewRef.current.zoom = zoom;
  viewRef.current.autoSpin = autoSpin;
  viewRef.current.showGrid = showGrid;
  viewRef.current.surveyMode = surveyMode;

  const selectedTile = useMemo(
    () => tiles.find((t) => t.id === selectedTileId) || tiles[0],
    [tiles, selectedTileId],
  );

  // Background spherical star catalogue (deterministic so it stays fixed on the sphere).
  const sphereStars = useMemo(() => {
    let seed = 404;
    const rand = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    return Array.from({ length: 220 }, () => ({
      ra: rand() * 360,
      dec: Math.asin(rand() * 2 - 1) * RAD2DEG,
      r: 0.7 + rand() ** 3 * 2.2,
      alpha: 0.3 + rand() * 0.7,
    }));
  }, []);

  // Full-sphere background mosaic patches (wraps the entire globe in space photos).
  const fullSpherePatches = useMemo(() => {
    const patches = [];
    const decBands = [-60, -20, 20, 60];
    let idx = 0;
    for (const dec of decBands) {
      const stepRa = Math.abs(dec) > 45 ? 60 : 45;
      for (let ra = 0; ra < 360; ra += stepRa) {
        const tile = tiles[idx % tiles.length];
        patches.push({
          ra: ra + stepRa / 2,
          dec,
          spanRa: stepRa + 2,
          spanDec: 42,
          imageUrl: tile.imageUrl,
        });
        idx++;
      }
    }
    return patches;
  }, [tiles]);

  // Fetch tiles from backend when configured.
  useEffect(() => {
    const controller = new AbortController();
    if (!isBackendConfigured()) {
      setSyncState('placeholder');
      return () => controller.abort();
    }

    setSyncState('loading');
    fetchSkyGlobeTiles({ signal: controller.signal })
      .then((data) => {
        setTiles(data);
        if (data[0]) setSelectedTileId(data[0].id);
        setSyncState('ready');
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setSyncState('error');
      });

    return () => controller.abort();
  }, []);

  // Preload tile images for canvas rendering.
  useEffect(() => {
    tiles.forEach((tile) => {
      if (!tile.imageUrl || imagesRef.current.has(tile.imageUrl)) return;
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = tile.imageUrl;
      imagesRef.current.set(tile.imageUrl, img);
    });
  }, [tiles]);

  // Smoothly center the 3D globe on a given (ra, dec).
  const focusCoordinates = (ra, dec) => {
    viewRef.current.targetRa = wrapDeg360(ra);
    viewRef.current.targetDec = clamp(dec, -80, 80);
    setCenterRa(viewRef.current.targetRa);
    setCenterDec(viewRef.current.targetDec);
  };

  const handleSelectTile = (tile) => {
    setSelectedTileId(tile.id);
    setAutoSpin(false);
    focusCoordinates(tile.ra, tile.dec);
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    const parts = searchInput
      .split(/[,\s]+/)
      .map((s) => parseFloat(s))
      .filter((n) => !Number.isNaN(n));
    if (parts.length >= 2) {
      setAutoSpin(false);
      focusCoordinates(parts[0], parts[1]);
    }
  };

  // Main 60fps 3D globe rendering loop.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    let rafId = 0;
    let lastUiSync = 0;

    const render = (now) => {
      const v = viewRef.current;

      // Smooth interpolation toward target coordinates or gentle auto-spin.
      if (!v.isDragging) {
        if (v.targetRa !== null && v.targetDec !== null) {
          let dRa = ((v.targetRa - v.ra + 540) % 360) - 180;
          let dDec = v.targetDec - v.dec;
          v.ra = wrapDeg360(v.ra + dRa * 0.12);
          v.dec = clamp(v.dec + dDec * 0.12, -82, 82);
          if (Math.hypot(dRa, dDec) < 0.15) {
            v.ra = v.targetRa;
            v.dec = v.targetDec;
            v.targetRa = null;
            v.targetDec = null;
          }
        } else if (v.autoSpin) {
          v.ra = wrapDeg360(v.ra + 0.14);
        }
      }

      if (now - lastUiSync > 120) {
        lastUiSync = now;
        setCenterRa(v.ra);
        setCenterDec(v.dec);
      }

      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth || canvas.parentElement?.clientWidth || 780;
      const h = canvas.clientHeight || canvas.parentElement?.clientHeight || 580;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h / 2;
      const baseRadius = Math.min(w, h) * 0.43 * v.zoom;

      const project = (raDeg, decDeg) => {
        const [x, y, z] = rotateForCamera(sphToVec(raDeg, decDeg), v.ra, v.dec);
        return {
          sx: cx + x * baseRadius,
          sy: cy - y * baseRadius,
          z,
        };
      };

      // 1. Outer atmospheric halo around the 3D celestial sphere
      const halo = ctx.createRadialGradient(cx, cy, baseRadius * 0.86, cx, cy, baseRadius * 1.18);
      halo.addColorStop(0, 'rgba(155, 95, 255, 0.25)');
      halo.addColorStop(0.6, 'rgba(90, 35, 175, 0.1)');
      halo.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, baseRadius * 1.18, 0, Math.PI * 2);
      ctx.fill();

      // 2. Clip everything inside the 3D sphere silhouette
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, baseRadius, 0, Math.PI * 2);
      ctx.clip();

      // Sphere deep-space core fill
      const coreGrad = ctx.createRadialGradient(
        cx - baseRadius * 0.28,
        cy - baseRadius * 0.28,
        baseRadius * 0.08,
        cx,
        cy,
        baseRadius,
      );
      coreGrad.addColorStop(0, '#2c1158');
      coreGrad.addColorStop(0.55, '#120528');
      coreGrad.addColorStop(1, '#04010c');
      ctx.fillStyle = coreGrad;
      ctx.fillRect(cx - baseRadius, cy - baseRadius, baseRadius * 2, baseRadius * 2);

      // Helper to warp a spherical photo patch onto the 3D globe surface
      const drawSphericalPhotoPatch = (
        raCenter,
        decCenter,
        spanRa,
        spanDec,
        imageUrl,
        alpha = 1,
        blendMode = 'screen',
      ) => {
        const img = imagesRef.current.get(imageUrl);
        if (!img || !img.complete || !img.naturalWidth) return;

        const cols = 3;
        const rows = 3;
        const iw = img.naturalWidth;
        const ih = img.naturalHeight;

        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.globalCompositeOperation = blendMode;
        for (let r = 0; r < rows; r++) {
          const v0 = r / rows;
          const v1 = (r + 1) / rows;
          const dec0 = decCenter + (0.5 - v0) * spanDec;
          const dec1 = decCenter + (0.5 - v1) * spanDec;

          for (let c = 0; c < cols; c++) {
            const u0 = c / cols;
            const u1 = (c + 1) / cols;
            const ra0 = raCenter + (u0 - 0.5) * spanRa;
            const ra1 = raCenter + (u1 - 0.5) * spanRa;

            const p00 = project(ra0, dec0);
            const p10 = project(ra1, dec0);
            const p01 = project(ra0, dec1);
            const p11 = project(ra1, dec1);

            if (p00.z < -0.05 && p10.z < -0.05 && p01.z < -0.05 && p11.z < -0.05) continue;

            drawTexturedTriangle(
              ctx,
              img,
              p00.sx,
              p00.sy,
              p10.sx,
              p10.sy,
              p11.sx,
              p11.sy,
              u0 * iw,
              v0 * ih,
              u1 * iw,
              v0 * ih,
              u1 * iw,
              v1 * ih,
            );
            drawTexturedTriangle(
              ctx,
              img,
              p00.sx,
              p00.sy,
              p11.sx,
              p11.sy,
              p01.sx,
              p01.sy,
              u0 * iw,
              v0 * ih,
              u1 * iw,
              v1 * ih,
              u0 * iw,
              v1 * ih,
            );
          }
        }
        ctx.restore();
      };

      // 3. Wrap the entire 3D sphere in continuous space photography (mosaic mode)
      if (v.surveyMode === 'mosaic') {
        for (const patch of fullSpherePatches) {
          drawSphericalPhotoPatch(
            patch.ra,
            patch.dec,
            patch.spanRa,
            patch.spanDec,
            patch.imageUrl,
            0.95,
            'screen',
          );
        }
      }

      // 4. Background stars rotating on the sphere
      for (const s of sphereStars) {
        const p = project(s.ra, s.dec);
        if (p.z <= 0) continue;
        ctx.fillStyle = `rgba(235, 224, 255, ${(s.alpha * p.z).toFixed(2)})`;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, s.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // 5. Render each Earth-matched space photograph tile on the sphere
      for (const tile of tiles) {
        const centerProj = project(tile.ra, tile.dec);
        if (centerProj.z <= 0.02) continue;

        const isSelected = tile.id === selectedTileId;
        const span = tile.angularSize || 38;

        drawSphericalPhotoPatch(
          tile.ra,
          tile.dec,
          span,
          span * 0.75,
          tile.imageUrl,
          1.0,
          'source-over',
        );
        drawSphericalPhotoPatch(
          tile.ra,
          tile.dec,
          span,
          span * 0.75,
          tile.imageUrl,
          isSelected ? 0.85 : 0.45,
          'screen',
        );

        // Draw curved tile boundary frame (like Aladin Lite FoV footprints)
        const halfRa = span / 2;
        const halfDec = (span * 0.75) / 2;
        const corners = [
          project(tile.ra - halfRa, tile.dec + halfDec),
          project(tile.ra + halfRa, tile.dec + halfDec),
          project(tile.ra + halfRa, tile.dec - halfDec),
          project(tile.ra - halfRa, tile.dec - halfDec),
        ];

        ctx.beginPath();
        corners.forEach((pt, idx) => {
          if (idx === 0) ctx.moveTo(pt.sx, pt.sy);
          else ctx.lineTo(pt.sx, pt.sy);
        });
        ctx.closePath();
        ctx.strokeStyle = isSelected
          ? 'rgba(255, 165, 100, 0.95)'
          : 'rgba(195, 155, 255, 0.45)';
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.stroke();

        // Tile center pin + label
        ctx.fillStyle = isSelected ? '#ff9a5c' : '#c9a6ff';
        ctx.beginPath();
        ctx.arc(centerProj.sx, centerProj.sy, isSelected ? 4.5 : 3, 0, Math.PI * 2);
        ctx.fill();

        if (centerProj.z > 0.32) {
          ctx.font = '500 11px "JetBrains Mono", monospace';
          ctx.fillStyle = isSelected ? '#ffd8be' : 'rgba(236, 230, 255, 0.82)';
          ctx.fillText(tile.title, centerProj.sx + 8, centerProj.sy + 4);
        }
      }

      // 6. Equatorial coordinate graticule (RA meridians & Dec parallels)
      if (v.showGrid) {
        ctx.strokeStyle = 'rgba(196, 162, 255, 0.2)';
        ctx.lineWidth = 1;

        // Meridians every 30° (2 hours of RA)
        for (let ra = 0; ra < 360; ra += 30) {
          ctx.beginPath();
          let penDown = false;
          for (let dec = -80; dec <= 80; dec += 5) {
            const p = project(ra, dec);
            if (p.z > 0) {
              if (!penDown) {
                ctx.moveTo(p.sx, p.sy);
                penDown = true;
              } else {
                ctx.lineTo(p.sx, p.sy);
              }
            } else {
              penDown = false;
            }
          }
          ctx.stroke();
        }

        // Parallels every 30° of Declination
        for (let dec = -60; dec <= 60; dec += 30) {
          ctx.beginPath();
          let penDown = false;
          for (let ra = 0; ra <= 360; ra += 5) {
            const p = project(ra, dec);
            if (p.z > 0) {
              if (!penDown) {
                ctx.moveTo(p.sx, p.sy);
                penDown = true;
              } else {
                ctx.lineTo(p.sx, p.sy);
              }
            } else {
              penDown = false;
            }
          }
          ctx.stroke();
        }
      }

      // 7. 3D spherical limb shading (darkens the horizon edge of the globe)
      const limbGrad = ctx.createRadialGradient(
        cx,
        cy,
        baseRadius * 0.55,
        cx,
        cy,
        baseRadius,
      );
      limbGrad.addColorStop(0, 'rgba(0, 0, 0, 0)');
      limbGrad.addColorStop(0.78, 'rgba(4, 1, 14, 0.25)');
      limbGrad.addColorStop(1, 'rgba(2, 0, 8, 0.82)');
      ctx.fillStyle = limbGrad;
      ctx.fillRect(cx - baseRadius, cy - baseRadius, baseRadius * 2, baseRadius * 2);
      ctx.restore();

      // Crisp outer rim of the 3D sphere
      ctx.strokeStyle = 'rgba(206, 174, 255, 0.42)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, baseRadius, 0, Math.PI * 2);
      ctx.stroke();

      // 8. Aladin-Lite center reticle crosshair
      ctx.strokeStyle = 'rgba(255, 140, 220, 0.85)';
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      ctx.moveTo(cx - 12, cy);
      ctx.lineTo(cx - 4, cy);
      ctx.moveTo(cx + 4, cy);
      ctx.lineTo(cx + 12, cy);
      ctx.moveTo(cx, cy - 12);
      ctx.lineTo(cx, cy - 4);
      ctx.moveTo(cx, cy + 4);
      ctx.lineTo(cx, cy + 12);
      ctx.stroke();

      rafId = requestAnimationFrame(render);
    };

    rafId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(rafId);
  }, [tiles, selectedTileId, fullSpherePatches, sphereStars]);

  // Pointer drag + click-to-select-tile on the 3D sphere.
  const onPointerDown = (e) => {
    const v = viewRef.current;
    v.isDragging = true;
    v.dragMoved = false;
    v.dragStartX = e.clientX;
    v.dragStartY = e.clientY;
    v.targetRa = null;
    v.targetDec = null;
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e) => {
    const v = viewRef.current;
    if (!v.isDragging) return;
    const dx = e.clientX - v.dragStartX;
    const dy = e.clientY - v.dragStartY;
    if (Math.hypot(dx, dy) > 4) v.dragMoved = true;
    v.dragStartX = e.clientX;
    v.dragStartY = e.clientY;

    const speed = 0.28 / v.zoom;
    v.ra = wrapDeg360(v.ra - dx * speed);
    v.dec = clamp(v.dec + dy * speed, -82, 82);
  };

  const onPointerUp = (e) => {
    const v = viewRef.current;
    if (!v.isDragging) return;
    v.isDragging = false;

    // If it was a click (not a drag), check if a tile on the front hemisphere was clicked.
    if (!v.dragMoved && canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const baseRadius = Math.min(rect.width, rect.height) * 0.41 * v.zoom;

      let closest = null;
      let minDist = 48;
      for (const tile of tiles) {
        const [x, y, z] = rotateForCamera(sphToVec(tile.ra, tile.dec), v.ra, v.dec);
        if (z <= 0.05) continue;
        const sx = cx + x * baseRadius;
        const sy = cy - y * baseRadius;
        const d = Math.hypot(clickX - sx, clickY - sy);
        if (d < minDist) {
          minDist = d;
          closest = tile;
        }
      }
      if (closest) {
        handleSelectTile(closest);
      }
    }
  };

  return (
    <div className="aladin-shell panel">
      {/* ---- Top Aladin-Lite style toolbar ---- */}
      <div className="aladin-toolbar">
        <div className="aladin-coords text-mono">
          <span className="aladin-coords__badge">ICRS</span>
          <span>
            {formatRA(centerRa)} · {formatDec(centerDec)}
          </span>
        </div>

        <form className="aladin-search" onSubmit={handleSearchSubmit}>
          <input
            type="text"
            className="aladin-search__input text-mono"
            placeholder="Go to RA, Dec (deg) e.g. 269.45, 4.69"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <button type="submit" className="aladin-search__btn text-label">
            Center
          </button>
        </form>

        <div className="aladin-toolbar__right">
          <select
            className="aladin-select text-caption"
            value={surveyMode}
            onChange={(e) => setSurveyMode(e.target.value)}
            aria-label="Sky layer mode"
          >
            <option value="mosaic">Layer: Full-Sphere Photo Mosaic</option>
            <option value="cutouts">Layer: Earth-Matched Cutouts Only</option>
          </select>

          <span className="aladin-status text-caption">
            <span className="aladin-status__dot" />
            {syncState === 'ready' ? 'Backend Geo-Sky Sync' : 'Placeholder Globe · 12 Tiles'}
          </span>
        </div>
      </div>

      {/* ---- Main Aladin viewport + Inspector split ---- */}
      <div className="aladin-stage">
        <div
          className="aladin-viewport"
          id="aladin-lite-viewport"
          data-slot="aladin-globe-viewport"
        >
          <canvas
            ref={canvasRef}
            className="aladin-canvas"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          />

          {/* Floating Aladin-Lite style zoom & layer controls */}
          <div className="aladin-controls" role="toolbar" aria-label="Globe controls">
            <button
              type="button"
              className="aladin-ctrl text-mono"
              onClick={() => setZoom((z) => clamp(Number((z + 0.2).toFixed(2)), 0.7, 2.4))}
              title="Zoom in"
            >
              +
            </button>
            <button
              type="button"
              className="aladin-ctrl text-mono"
              onClick={() => setZoom((z) => clamp(Number((z - 0.2).toFixed(2)), 0.7, 2.4))}
              title="Zoom out"
            >
              −
            </button>
            <button
              type="button"
              className={`aladin-ctrl text-caption${autoSpin ? ' is-active' : ''}`}
              onClick={() => setAutoSpin((s) => !s)}
              title="Toggle sphere auto-rotation"
            >
              Spin
            </button>
            <button
              type="button"
              className={`aladin-ctrl text-caption${showGrid ? ' is-active' : ''}`}
              onClick={() => setShowGrid((g) => !g)}
              title="Toggle Equatorial RA/Dec grid"
            >
              Grid
            </button>
            <button
              type="button"
              className="aladin-ctrl text-caption"
              onClick={() => {
                setZoom(1.0);
                setAutoSpin(true);
              }}
              title="Reset view"
            >
              Reset
            </button>
          </div>

          <div className="aladin-hint text-caption text-muted">
            Drag to rotate 3D sky sphere · Click any photo tile to inspect Earth capture origin
          </div>
        </div>

        {/* ---- Right-side Earth -> Sky Tile Inspector ---- */}
        {selectedTile && (
          <aside className="aladin-inspector">
            <div className="aladin-inspector__preview">
              <img src={selectedTile.imageUrl} alt={selectedTile.title} />
              <span className="aladin-inspector__tag text-mono">{selectedTile.band}</span>
            </div>

            <div className="aladin-inspector__body">
              <p className="text-label text-accent">Selected Sky Photograph</p>
              <h3 className="text-h2">{selectedTile.title}</h3>

              <div className="aladin-inspector__meta">
                <div>
                  <span className="text-caption text-muted">Sky Coordinates (RA / Dec)</span>
                  <p className="text-mono">
                    {selectedTile.ra.toFixed(2)}°, {selectedTile.dec.toFixed(2)}°
                  </p>
                </div>
                <div>
                  <span className="text-caption text-muted">Captured on Earth (Station)</span>
                  <p className="text-small">{selectedTile.earthSite}</p>
                </div>
                <div>
                  <span className="text-caption text-muted">Earth Lat / Lon</span>
                  <p className="text-mono">
                    {selectedTile.earthLat.toFixed(4)}°, {selectedTile.earthLon.toFixed(4)}°
                  </p>
                </div>
                <div>
                  <span className="text-caption text-muted">Observation Time (UTC)</span>
                  <p className="text-mono">
                    {new Date(selectedTile.capturedAt).toUTCString()}
                  </p>
                </div>
              </div>

              <button
                type="button"
                className="btn-primary text-label aladin-inspector__cta"
                onClick={() => navigate(ROUTES.player)}
              >
                Open in Dashboard →
              </button>
            </div>
          </aside>
        )}
      </div>

      {/* ---- Quick tile selector strip ---- */}
      <div className="aladin-strip" aria-label="Mapped sky photographs">
        {tiles.map((tile) => (
          <button
            key={tile.id}
            type="button"
            className={`aladin-chip text-caption${tile.id === selectedTileId ? ' is-active' : ''}`}
            onClick={() => handleSelectTile(tile)}
          >
            <span className="aladin-chip__dot" />
            <span>{tile.title}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

