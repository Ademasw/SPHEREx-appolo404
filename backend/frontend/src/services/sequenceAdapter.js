// Pure contract adapter: never substitutes demo images for archive data.
export function normalizeSequence(states, { coordinates = '', settings = {} } = {}, url = x => x) {
  const available = states.map(s => s.manifest);
  const selected = 'D' + (settings.displayDetector || available[0].query.detector.slice(1));
  const manifests = available.filter(m => m.query.detector === selected);
  if (!manifests.length) throw new Error('Selected detector is unavailable');
  const frames = manifests.flatMap(m => (m.frames || []).map(f => ({ ...f, detector: m.query.detector })))
    .sort((a, b) => a.time_utc.localeCompare(b.time_utc));
  const first = manifests[0];
  const visits = (first.visits?.length ? first.visits : first.frames || []).slice()
    .sort((a, b) => a.time_utc.localeCompare(b.time_utc));
  const nearest = (date, fallback) => date && visits.length
    ? visits.reduce((best, v) => Math.abs(Date.parse(v.time_utc + 'Z') - Date.parse(date)) < Math.abs(Date.parse(best.time_utc + 'Z') - Date.parse(date)) ? v : best)
    : fallback;
  const chosen = [nearest(settings.epoch1Date, visits[0]), nearest(settings.epoch2Date, visits.at(-1))];
  const sharedWavelength = chosen[0] && chosen[1]
    ? { min: Math.max(chosen[0].wavelength_min_um ?? -Infinity, chosen[1].wavelength_min_um ?? -Infinity),
        max: Math.min(chosen[0].wavelength_max_um ?? Infinity, chosen[1].wavelength_max_um ?? Infinity) }
    : null;
  const key = first.query.key;
  const colourReady = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6'].every(det => available.some(m => m.query.detector === det));
  return {
    coordinates, source: 'backend', updatedAt: first.created_at,
    player: { frameMetadata: frames.map(f => ({date:f.time_utc, detector:f.detector, wavelength:f.wavelength_um, maskUrl:f.mask_url ? url(f.mask_url) : null})), mode: 'frames', frames: frames.map(f => url(f.image_url)), fps: Number(settings.playerFps) || 3, videoUrl: null, streamUrl: null },
    compare: { availableEpochs: visits.map(v => v.time_utc), epochs: chosen.map((v, i) => ({ id: String(i), label: settings[`epoch${i + 1}Label`] || `Epoch ${i + 1}`,
      date: v?.time_utc || 'No observation', imageUrl: v ? url(v.image_url) : '',
      meta: `${first.query.detector} · nearest available observation${chosen[0] && chosen[0] === chosen[1] ? ' · same observation for both dates' : ''}` })) },
    science: {
      sequenceKey: key,
      quality: visits.map((visit, index) => ({ index, coverage: visit.usable_grid_fraction, frames: visit.n_frames,
        level: visit.usable_grid_fraction >= .85 && visit.n_frames >= 8 ? 'good' : visit.usable_grid_fraction >= .55 && visit.n_frames >= 3 ? 'partial' : 'poor' })),
      sharedWavelength: sharedWavelength && Number.isFinite(sharedWavelength.min) && Number.isFinite(sharedWavelength.max) && sharedWavelength.max > sharedWavelength.min ? sharedWavelength : null,
      spectrumUrl: `/api/science/${key}/spectrum`,
      colourUrl: colourReady ? `/api/science/${key}/colour/0.png` : null,
      matchedDifferenceUrl: chosen[0] && chosen[1] ? `/api/sequence/${key}/${first.query.detector}/pair/${visits.indexOf(chosen[0])}/${visits.indexOf(chosen[1])}.png` : null,
      epsilonPanel: /epsilon/i.test(first.target?.name || '') ? { summaryUrl: '/api/epsilon', motionUrl: '/api/epsilon/motion' } : null,
    },
    metadata: {
      'Target Coordinates': `${first.query.ra_deg}, ${first.query.dec_deg}`,
      'Motion Reference': first.target?.motion_source || first.target?.source || 'No catalog proper motion applied',
      ...(first.target?.gaia ? { 'Gaia DR3': `${first.target.gaia.source_id} · RUWE ${first.target.gaia.ruwe ?? '—'} · ${first.target.gaia.separation_arcsec?.toFixed(2) ?? '—'}″ match` } : {}),
      'Detector Arrays': available.map(m => m.query.detector).join(', '),
      'Displayed Detector': selected,
      'Field of View': `${first.query.fov_deg * 60} arcmin`,
      'Pixel Scale': `${first.grid?.pixel_arcsec ?? '—'} arcsec / px`,
      'Frame Count': frames.length,
      'Processing': first.processing?.steps?.join('; ') || 'See archive manifest',
      'Warnings': [...new Set(manifests.flatMap(m => m.warnings || []))].join(' '),
      'Epoch selection': 'Nearest available visit; dates do not request new archive epochs. Comparison uses the first selected detector.',
      'Zodi Subtraction': 'Fixed backend processing: supplied ZODI + sky median; saturated cores excluded',
    },
  };
}
