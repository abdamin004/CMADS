# CMADS Doctor Console

A production-style clinical review UI for the CMADS thesis system.

The console has two parts:

- `backend/`: FastAPI API that reads Gold-layer patient cases and saved MAS run artifacts.
- `frontend/`: React + Vite UI for patient selection, agent workflow inspection, shared-memory timeline, diagnosis, and treatment review.

The default view opens the case-based memory run when it is available, surfaces saved-run patients first, and shows cohort-level DIRECT/INDIRECT/MISS performance before patient drill-down.

## Run Locally

Backend:

```bash
python3 -m uvicorn doctor_console.backend.app:app --reload --host 127.0.0.1 --port 8010
```

Frontend:

```bash
cd doctor_console/frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

You can also use:

```bash
make doctor-console-api
make doctor-console-web
```

## Notes

- The UI reads existing `data/gold/mas_results*` folders.
- The live run button calls the existing Python pipeline and saves to `data/gold/mas_results`.
- The frontend never reads ground-truth data as agent input; ground truth is displayed only in the evaluation panel for thesis auditability.
