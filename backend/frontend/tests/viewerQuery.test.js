import test from 'node:test';
import assert from 'node:assert/strict';
import { parseViewerQuery, updateViewerQuery } from '../src/services/viewerQuery.js';
test('zero coordinates, URL settings and unknown parameters survive updates', () => {
  const parsed = parseViewerQuery('?ra=0&dec=0&bg=median&fps=7&label1=Before');
  assert.equal(parsed.q, '0 0'); assert.equal(parsed.bg, 'median');
  assert.equal(parsed.playerFps, 7); assert.equal(parsed.epoch1Label, 'Before');
  const search = updateViewerQuery('?epoch1=2025-01-01&custom=yes&ra=0&dec=0', { q: 'Barnard', frame: 2 });
  const p = new URLSearchParams(search);
  assert.equal(p.get('epoch1'), '2025-01-01'); assert.equal(p.get('custom'), 'yes');
  assert.equal(p.has('ra'), false); assert.equal(parseViewerQuery(search).frame, 2);
});
test('invalid URLs never silently select another target or mode', () => {
  for (const search of ['?ra=1', '?ra=&dec=0', '?ra=NaN&dec=0', '?ra=360&dec=0', '?view=bad', '?frame=Infinity', '?a=1.2', '?fov=9', '?v=2', '?epoch1=invalid'])
    assert.throws(() => parseViewerQuery(search), undefined, search);
  assert.equal(parseViewerQuery('?q=Named&ra=invalid').q, 'Named');
});
