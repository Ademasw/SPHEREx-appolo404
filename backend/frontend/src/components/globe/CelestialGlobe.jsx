import { useEffect, useRef, useState } from 'react';
import './CelestialGlobe.css';

// Explicit IRSA URL prevents the default DSS survey or a CDS survey mirror.
export const IRSA_SURVEY = 'https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/RGB-W4-W2-W1';
// The visible circular aperture is 85.6% of the square canvas.
// Keep the SIN sphere slightly larger at the furthest allowed zoom.
const MAX_FOV = 209;
let library;
function loadAladin() {
  if (!library) library = import('aladin-lite').then(async ({ default: A }) => { await A.init; return A; });
  return library;
}

export default function CelestialGlobe() {
  const container = useRef(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    let viewer;
    let maxZoomFactor;
    const element = container.current;
    // SIN can keep reporting 180° while its projected sphere gets smaller.
    // Clamp the actual zoom synchronously, including inertial wheel/pinch frames.
    const clampZoom = () => {
      if (viewer && maxZoomFactor && viewer.getZoomFactor() > maxZoomFactor) {
        viewer.setZoomFactor(maxZoomFactor);
      }
    };
    loadAladin().then(A => {
      if (cancelled) return;
      viewer = A.aladin(container.current, {
        survey: A.imageHiPS(IRSA_SURVEY, {
          successCallback: () => { requestAnimationFrame(() => { if (!cancelled && viewer) viewer.setFoV(MAX_FOV); }); },
        }),
        target: '266.4 -29.0', fov: MAX_FOV, projection: 'SIN', backgroundColor: '#000000',
        inertia: true,
        showLayersControl: false, showZoomControl: false, showGotoControl: false,
        showFullscreenControl: false, showSimbadPointerControl: false,
        showCooGridControl: false, showSettingsControl: false,
        showSelectionModeControl: false, showColorPickerControl: false,
        showShareControl: false, showStatusBar: false,
        showFrame: false, showFov: false, showCooLocation: false,
        showProjectionControl: false, showContextMenu: false,
        showReticle: false, showCatalog: false, showCooGrid: false,
      });
      viewer.setFoVRange(0.05, MAX_FOV);
      viewer.setFoV(MAX_FOV);
      maxZoomFactor = viewer.getZoomFactor();
      element.addEventListener('AL:zoom.changed', clampZoom);
      viewer.setBackgroundColor('#000000');
      requestAnimationFrame(() => { if (!cancelled) { viewer.setFoV(MAX_FOV); viewer.setBackgroundColor('#000000'); } });
    }).catch(err => { if (!cancelled) setError(err.message || 'The sky map requires WebGL2 and an internet connection.'); });
    return () => { cancelled = true; element.removeEventListener('AL:zoom.changed', clampZoom); viewer?.remove(); };
  }, []);
  return <div className="irsa-sky-map" aria-label="NASA IPAC IRSA AllWISE sky map. Drag to pan and scroll or pinch to zoom.">
    <div ref={container} className="irsa-sky-map__canvas" />
    {error && <p className="irsa-sky-map__error" role="alert">{error}</p>}
  </div>;
}
