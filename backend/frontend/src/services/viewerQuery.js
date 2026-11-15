// Shared v1 contract. Unknown keys are preserved when updating a link.
export function parseViewerQuery(search) {
  const p = new URLSearchParams(search);
  if (p.has('v') && p.get('v') !== '1') throw new Error('Unsupported viewer URL version');
  let q = p.get('q')?.trim() || '';
  if (!q && (p.has('ra') || p.has('dec'))) {
    const ra = Number(p.get('ra')), dec = Number(p.get('dec'));
    if (!p.get('ra')?.trim() || !p.get('dec')?.trim() || !Number.isFinite(ra) || !Number.isFinite(dec) || ra < 0 || ra >= 360 || dec < -90 || dec > 90)
      throw new Error('Provide RA [0, 360) and Dec [-90, 90] together in degrees');
    q = `${ra} ${dec}`;
  }
  const choice = (key, allowed, fallback) => {
    const value = p.get(key);
    if (value !== null && !allowed.includes(value)) throw new Error(`Invalid ${key} in viewer URL`);
    return value ?? fallback;
  };
  const index = key => {
    if (!p.has(key)) return null;
    if (!/^\d+$/.test(p.get(key)) || !Number.isSafeInteger(Number(p.get(key)))) throw new Error(`Invalid ${key} index`);
    return Number(p.get(key));
  };
  const boolean = (key, fallback) => choice(key, ['true', 'false'], String(fallback)) === 'true';
  const epoch = key => {
    const value = p.get(key) || '';
    if (value && !Number.isFinite(Date.parse(value))) throw new Error(`Invalid ${key} date`);
    return value;
  };
  return { q, det: choice('det', ['D1','D2','D3','D4','D5','D6','all'], 'D6'),
    fov: Number(choice('fov', ['0.05','0.1','0.2'], '0.1')),
    bg: choice('bg', ['model','median','none'], 'model'),
    clean: boolean('clean', false), smooth: boolean('smooth', true),
    view: choice('view', ['visits','frames','compare','difference'], 'visits'),
    cmp: choice('cmp', ['side','blink','diff'], 'side'),
    frame: index('frame') ?? 0, a: index('a'), b: index('b'),
    epoch1: epoch('epoch1'), epoch2: epoch('epoch2'),
    epoch1Label: p.get('label1') || 'Epoch 1', epoch2Label: p.get('label2') || 'Epoch 2',
    displayDetector: choice('displayDet', ['1','2','3','4','5','6'], '1'),
    playerFps: Number(choice('fps', ['1','2','3','4','5','6','7','8','9','10','12','15','24','30'], '3')) };
}

export function updateViewerQuery(search, values) {
  const p = new URLSearchParams(search);
  p.set('v', '1');
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined || value === '') p.delete(key);
    else p.set(key, String(value));
  }
  if (values.q !== undefined) { p.delete('ra'); p.delete('dec'); }
  return '?' + p;
}
