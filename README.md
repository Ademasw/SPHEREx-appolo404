# Apollo 404 — SPHEREx Explorer

FastAPI + React viewer for real NASA/IPAC IRSA spectral images. The maintained application is in `backend/`; `front/front` is a historical design prototype.

Work is published to the `prod` branch. Installation and API usage: [backend README](backend/README.md). Current implementation, validation and remaining scientific work: [work report](backend/docs/work-report-2026-11-15.ru.md). Reproducible real-data provenance: [validation JSON](backend/docs/validation-prod-2026-11-15.json).

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [the viewer](http://127.0.0.1:8000/dashboard/advanced) or [API documentation](http://127.0.0.1:8000/docs). Python 3.12 is used for validation. On Windows, use the installed Python executable's full path if the Store alias or launcher fails.

FITS, `.venv`, `node_modules`, builds and scientific caches are generated locally and excluded from Git. A fresh clone downloads actual data when requested. `docker compose up --build` uses the backend context and a persistent `backend/data` volume; Docker Engine must be running.

This is an exploratory tool. Spectral ranges, aperture measurements and differences are diagnostic; they do not establish a discovery, calibrated spectrum or significant motion measurement.
