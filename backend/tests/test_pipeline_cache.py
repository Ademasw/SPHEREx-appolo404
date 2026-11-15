import json
import threading
from datetime import datetime, timezone

import pytest

from app import pipeline
from app.jobs import JobManager
from app.releases import configured_collections


def test_releases_reject_unknown_schema_and_remove_duplicates():
    assert configured_collections('spherex_dr1,spherex_dr1,spherex_qr3') == ('spherex_dr1', 'spherex_qr3')
    with pytest.raises(ValueError, match='reviewed'):
        configured_collections('spherex_future')


def test_corrupt_and_old_result_cache_is_not_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'SEQUENCES', tmp_path)
    root = pipeline.output_dir(10, 0, 'D6', .1)
    root.mkdir(parents=True)
    path = root / 'manifest.json'
    path.write_text('{')
    assert pipeline.load(10, 0, 'D6', .1) is None
    path.write_text(json.dumps({'cache_version': 'old'}))
    assert pipeline.load(10, 0, 'D6', .1) is None
    path.write_text(json.dumps({'cache_version': pipeline.CACHE_VERSION}))
    assert pipeline.load(10, 0, 'D6', .1)['cache_version'] == pipeline.CACHE_VERSION


def test_failed_refresh_keeps_published_result_and_coalesces_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'SEQUENCES', tmp_path)
    root = pipeline.output_dir(10, 0, 'D6', .1)
    root.mkdir(parents=True)
    previous = {'created_at': datetime.now(timezone.utc).isoformat(), 'cache_version': pipeline.CACHE_VERSION}
    path = root / 'manifest.json'
    path.write_text(json.dumps(previous))
    started, finish = threading.Event(), threading.Event()
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs)
        started.set()
        finish.wait(5)
        raise pipeline.PipelineError('Archive unavailable')
    monkeypatch.setattr(pipeline, 'run', fail)
    manager = JobManager(workers=1)
    try:
        manager.request(10, 0, 'D6', .1, refresh=True)
        assert started.wait(2)
        assert manager.request(10, 0, 'D6', .1, refresh=True)['status'] == 'running'
        assert manager.request(10, 0, 'D6', .1)['status'] == 'running'
    finally:
        finish.set()
        manager._pool.shutdown(wait=True)
    assert len(calls) == 1 and calls[0]['refresh']
    assert json.loads(path.read_text()) == previous
    assert manager.request(10, 0, 'D6', .1)['manifest'] == previous


def test_fast_worker_returns_manifest_even_if_it_finishes_before_submit_returns(monkeypatch):
    published=[]
    monkeypatch.setattr(pipeline,'load',lambda *args:published[0] if published else None)
    monkeypatch.setattr(pipeline,'run',lambda *args,**kwargs:published.append({'frames':[]}))
    manager=JobManager(workers=1)
    manager._pool.shutdown()
    class ImmediatePool:
        def submit(self, function, *args):
            function(*args)
    manager._pool=ImmediatePool()
    assert manager.request(10,0,'D6',.1)=={'status':'done','manifest':{'frames':[]}}


def test_render_failure_does_not_modify_published_generation(tmp_path, monkeypatch):
    import numpy as np
    from app.preview import make_grid
    monkeypatch.setattr(pipeline,'SEQUENCES',tmp_path)
    root=pipeline.output_dir(10,0,'D6',.05)
    root.mkdir(parents=True)
    (root/'manifest.json').write_text('{"generation":"'+'a'*32+'"}')
    previous=(root/'generations'/('a'*32)/'frames')
    previous.mkdir(parents=True)
    (previous/'0.png').write_bytes(b'previous image')
    row={'obs_id':'test','detector':'D6','t_min':60000.,'collection':'spherex_dr1'}
    monkeypatch.setattr(pipeline,'query_observations',lambda *args,**kwargs:{'observations':[row],'retrieved_at':'2026-01-01'})
    monkeypatch.setattr(pipeline,'download_all',lambda *args:([(row,'url',tmp_path/'input')],[],{}))
    monkeypatch.setattr(pipeline,'wavetable',lambda *args:None)
    _,size=make_grid(10,0,.05)
    data=np.ones((size,size))
    flags=np.zeros((size,size),dtype=bool)
    monkeypatch.setattr(pipeline,'process_frame',lambda *args:(data,data,flags,flags,4.,.1,0.,0.,['NONFUNC'],data*4,data*.1,data*0,{'MSKN0006':'NONFUNC'}))
    def broken_render(*args,**kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(pipeline,'render',broken_render)
    with pytest.raises(OSError,match='disk full'):
        pipeline.run(10,0,'D6',.05,refresh=True)
    assert (previous/'0.png').read_bytes()==b'previous image'
    assert json.loads((root/'manifest.json').read_text())['generation']=='a'*32


def test_published_generation_is_resolved_without_touching_legacy_data(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'SEQUENCES', tmp_path)
    root = tmp_path / 'key' / 'D6'
    root.mkdir(parents=True)
    assert pipeline.product_dir('key', 'D6') == root
    generation = 'a' * 32
    (root / 'manifest.json').write_text(json.dumps({'generation': generation}))
    assert pipeline.product_dir('key', 'D6') == root / 'generations' / generation


@pytest.mark.parametrize('ra,dec', [(0.,0.),(359.99,89.9)])
def test_archive_queries_cover_field_and_deduplicate_observation_identity(tmp_path, monkeypatch, ra, dec):
    from astropy.table import Table
    monkeypatch.setattr(pipeline,'METADATA',tmp_path)
    rows=Table(rows=[('same-id','SPHEREx-D6','https://example/one',60000.,60001.,'spherex_dr1',4e-6,5e-6),
                     ('same-id','SPHEREx-D6','https://example/two',60000.,60001.,'spherex_qr3',4e-6,5e-6)],
               names=['obs_id','energy_bandpassname','access_url','t_min','t_max','obs_collection','em_min','em_max'])
    calls=[]
    def query(**kwargs):
        calls.append(kwargs)
        return rows
    monkeypatch.setattr(pipeline.Irsa,'query_sia',query)
    result=pipeline.query_observations(ra,dec,.2)
    assert len(result['observations'])==1
    assert calls[0]['pos'][1].deg > .14
    assert pipeline.query_observations(ra,dec,.2)==result
    assert len(calls)==1
    assert not list(tmp_path.glob('*.tmp'))
