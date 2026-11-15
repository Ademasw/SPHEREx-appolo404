import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeSequence } from '../src/services/sequenceAdapter.js';
const state = (detector = 'D6') => ({ manifest: {
 query: {ra_deg: 10, dec_deg: -20, detector, fov_deg: .1},
 frames: [{time_utc:'2025-11-01T00:00:00', image_url:'/b.png'}, {time_utc:'2025-05-01T00:00:00', image_url:'/a.png'}],
 visits: [{time_utc:'2025-05-02T00:00:00', image_url:'/v1.png'}, {time_utc:'2025-11-02T00:00:00', image_url:'/v2.png'}],
 warnings: ['Spectral changes are not motion'], processing: { steps: ['IMAGE-ZODI'] },
} });
test('real URLs sorted chronologically; actual nearest dates and labels preserved', () => {
 const result = normalizeSequence([state()], {settings:{epoch1Date:'2025-05-01',epoch2Date:'2025-11-01',epoch1Label:'First',playerFps:7}}, x => 'https://example.test'+x);
 assert.deepEqual(result.player.frames,['https://example.test/a.png','https://example.test/b.png']);
 assert.equal(result.compare.epochs[0].date,'2025-05-02T00:00:00');
 assert.equal(result.compare.epochs[0].label,'First');
 assert.equal(result.compare.epochs[1].imageUrl,'https://example.test/v2.png');
 assert.equal(result.player.fps,7);
 assert.match(result.metadata.Warnings,/Spectral/);
});
test('empty archive never becomes demo data', () => {
 const s=state();s.manifest.frames=[];s.manifest.visits=[];
 const result=normalizeSequence([s]);assert.deepEqual(result.player.frames,[]);
 assert.equal(result.compare.epochs[0].imageUrl,'');
});
test('all arrays keep playback and comparison on the same selected detector', () => {
 const result=normalizeSequence([state('D1'),state('D2')], {settings:{displayDetector:'2'}});
 assert.equal(result.player.frames.length,2);
 assert.equal(result.metadata['Detector Arrays'],'D1, D2');
 assert.match(result.compare.epochs[0].meta,/D2/);
});
test('same nearest visit is explicitly reported', () => {
 const result=normalizeSequence([state()],{settings:{epoch1Date:'2025-05-01',epoch2Date:'2025-05-03'}});
 assert.match(result.compare.epochs[1].meta,/same observation/);
});
