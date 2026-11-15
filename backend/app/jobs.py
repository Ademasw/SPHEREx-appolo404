"""Background jobs for the on-demand pipeline, with progress for the viewer.

A job is identified by (position key, detector). Asking again for a job that
is running returns its progress; a finished one is read from disk.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app import pipeline

RESULT_TTL_S = 7 * 24 * 3600  # SPHEREx data arrive weekly


class JobManager:
    def __init__(self, workers=2, max_pending=6):
        self._pool = ThreadPoolExecutor(workers)
        self._jobs = {}
        self._lock = threading.Lock()
        self._max_pending = max_pending

    def request(self, ra, dec, detector, fov, target=None, background="model", clean=False, smooth=True, refresh=False):
        """Return the finished manifest, or the state of the (possibly new) job."""
        job_id = f"{pipeline.sequence_key(ra, dec, fov, background, clean, smooth)}/{detector}"
        with self._lock:
            state = self._jobs.get(job_id)
            if state and state["status"] in ("queued", "running"):
                return self._public(state)
            manifest = pipeline.load(ra, dec, detector, fov, background, clean, smooth)
            if not refresh and manifest and not self._stale(manifest):
                return {"status": "done", "manifest": manifest}
            if state and state["status"] == "error" and time.time() - state["finished"] < 30:
                return self._public(state)  # do not hammer IRSA with immediate retries
            self._jobs = {key: value for key, value in self._jobs.items()
                          if value["finished"] is None or time.time() - value["finished"] < 300}
            if sum(s["status"] in ("queued", "running") for s in self._jobs.values()) >= self._max_pending:
                return {"status": "error", "error": "Processing queue is full; try again shortly"}
            state = {"id": job_id, "status": "queued", "stage": "queued", "done": 0, "total": 0,
                     "started": time.time(), "error": None, "finished": None}
            self._jobs[job_id] = state
        self._pool.submit(self._run, state, ra, dec, detector, fov, target, background, clean, smooth, refresh)
        public = self._public(state)
        if public['status'] == 'done':
            manifest = pipeline.load(ra, dec, detector, fov, background, clean, smooth)
            if manifest:
                return {'status': 'done', 'manifest': manifest}
            public['status'] = 'running'  # poll once more; never claim a result without its manifest
        return public

    def _run(self, state, ra, dec, detector, fov, target, background="model", clean=False, smooth=True, refresh=False):
        def progress(stage, done, total):
            state.update(status="running", stage=stage, done=done, total=total)
        try:
            state["status"] = "running"
            pipeline.run(ra, dec, detector, fov, target=target, progress=progress, background=background, clean=clean, smooth=smooth, refresh=refresh)
            state["status"] = "done"
        except pipeline.PipelineError as error:
            state.update(status="error", error=str(error))
        except Exception as error:  # unexpected: keep the server alive, report briefly
            state.update(status="error", error=f"Processing failed ({type(error).__name__})")
        finally:
            state["finished"] = time.time()

    @staticmethod
    def _stale(manifest):
        from datetime import datetime
        try:
            created = datetime.fromisoformat(manifest["created_at"]).timestamp()
        except (KeyError, ValueError, TypeError):
            return True
        return time.time() - created > RESULT_TTL_S

    @staticmethod
    def _public(state):
        return {"status": state["status"], "stage": state["stage"], "done": state["done"],
                "total": state["total"], "elapsed_s": round(time.time() - state["started"], 1),
                "error": state["error"]}
