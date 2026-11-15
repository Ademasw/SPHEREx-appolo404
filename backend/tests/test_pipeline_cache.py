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


def test_published_generation_is_resolved_without_touching_legacy_data(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'SEQUENCES', tmp_path)
    root = tmp_path / 'key' / 'D6'
    root.mkdir(parents=True)
    assert pipeline.product_dir('key', 'D6') == root
    generation = 'a' * 32
    (root / 'manifest.json').write_text(json.dumps({'generation': generation}))
    assert pipeline.product_dir('key', 'D6') == root / 'generations' / generation
