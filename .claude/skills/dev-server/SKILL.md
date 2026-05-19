---
name: dev-server
description: Start, stop, or check status of local backend and frontend dev servers.
trigger: User asks to start, stop, restart, or check local dev servers.
---

# Local Dev Servers

The app has two servers: a FastAPI backend (port 8000) and a Vite React frontend (port 5173). The frontend proxies `/api` requests to the backend.

## Start

Start both servers in the background:

```bash
# Backend (FastAPI)
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

```bash
# Frontend (Vite)
cd frontend && npm run dev
```

Run each in a separate background shell. The backend reads `LAKEBASE_BRANCH_ID` from `.env` (typically `dev-{first-last}`). To target a different branch for a one-off run:

```bash
LAKEBASE_BRANCH_ID=dev-taylor-isbell uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

## Stop

Kill processes on the dev ports:

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null; lsof -ti:5173 | xargs kill -9 2>/dev/null
```

## Status

Check what's running on each port:

```bash
lsof -i:8000
lsof -i:5173
```

## Restart

Stop then start again. Use the stop commands above, then re-launch both servers.

## Key Details

- Backend: port 8000, entry point `app:app`
- Frontend: port 5173, directory `frontend/`
- `.env` should have `DATABRICKS_CONFIG_PROFILE=todo-app-dev`
- Both servers must be running for the full app to work
- Frontend Vite config proxies `/api` to `http://localhost:8000`
