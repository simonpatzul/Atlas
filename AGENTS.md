# Repository Guidelines

## Project Structure & Module Organization

This workspace has three active surfaces:

- Frontend app at the repo root: `main.jsx`, `index.html`, `vite.config.js`, and the main React feature file `remixed-f545b974.tsx`.
- Backend service in `atlas-data/`: `main.py` (FastAPI app), `engine.py`, `models.py`, `scoring.py`, `cache.py`, `collectors/`, `dashboard.html`, and MT4 examples under `atlas-data/examples/`.
- Deployment adapters at the repo root: `api/index.py`, `vercel.json`, `requirements.txt`, `Dockerfile.web`, `render.yaml`, and deployment guides.

Build output goes to `dist/`. Treat `README.md` as product/spec context, not as a reliable map of the current codebase.

## Current Product Behavior

ATLAS is a trading context platform for FX/metals. It combines market data, macro context, news/event risk, COT, sentiment, technical scoring, Monte Carlo prediction, and MT4 integration.

The backend now returns multi-horizon context:

- `timeframe_5m`, `timeframe_1h`, `timeframe_1d` on `/context/{symbol}`.
- MT4-friendly top-level fields on `/mt4/context/{symbol}` and flat endpoint `/?symbol=EURUSD`.
- Horizon fields include `bias_*`, `confidence_*`, `score_adjust_*`, `tradeable_*`, and `expected_range_*_pips`.
- Legacy top-level `bias`, `confidence`, `score_adjust`, and `tradeable` represent the `1H` layer for compatibility.

The frontend supports prediction horizons `5M`, `1H`, and `1D`. It uses `timeframe_5m`, `timeframe_1h`, and `timeframe_1d` for the selected prediction horizon. The frontend automatically uses `/api` as API base on `.vercel.app`, or `VITE_ATLAS_API_BASE` when provided.

The MT4 EA strategy now defaults to API-driven triple alignment:

- `RequireTripleAlignment = true`
- `RequireLocalConfirmation = false`
- Opens only when `bias_5m == bias_1h == bias_1d` and the shared bias is not `NEUTRAL`.
- Closes on API disagreement if `CloseOnApiDisagreement = true`.
- Includes emergency stop and trailing stop controls.
- Shows a status panel on the chart when `ShowStatusPanel = true`.

## Build, Test, and Development Commands

- `npm run dev` - starts the Vite frontend on `http://localhost:5173`.
- `npm run build` - creates the production frontend bundle in `dist/`.
- `npm run preview` - serves the built frontend locally.
- `cd atlas-data; .\.venv\Scripts\activate; uvicorn main:app --host 127.0.0.1 --port 8000` - runs the FastAPI service locally.
- `atlas-data\start.bat` - Windows helper that creates `.venv`, installs dependencies, and starts the API.
- `cmd /c npm run dev` - prefer this on Windows if PowerShell blocks `npm.ps1`.

There is no configured root test, lint, or format script at the moment.

## Local Runtime

Local frontend and backend run separately:

- Frontend: `http://localhost:5173`
- Backend: `http://127.0.0.1:8000`
- Vite proxy maps `/health`, `/context`, `/context-all`, `/market`, and `/mt4` to the local backend.

Useful local checks:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/context/EURUSD`
- `http://127.0.0.1:8000/mt4/context/EURUSD`
- `http://127.0.0.1:8000/?symbol=EURUSD`

`atlas-launch.bat` opens backend, frontend, and then the browser.

## Deployment Notes

GitHub repo:

- `https://github.com/simonpatzul/Atlas`

Vercel is the current free deployment target:

- Root Directory: repo root (`./` or default).
- Framework Preset: `Vite`.
- Build Command: `npm run build`.
- Output Directory: `dist`.
- Root `requirements.txt` must list Python dependencies explicitly; do not use `-r atlas-data/requirements.txt` because Vercel failed parsing that include.
- `api/index.py` exposes the FastAPI `app` from `atlas-data/main.py`.
- `vercel.json` rewrites `/api/*`, `/health`, `/context/*`, `/context-all`, `/market/*`, and `/mt4/*` to the Vercel Python function.

Vercel environment variables:

- `VITE_ATLAS_API_BASE=/api`
- `CORS_ORIGINS=*`
- `CACHE_DB=/tmp/atlas-cache.db`
- Optional: `FRED_API_KEY`
- Optional: `ALPHA_API_KEY`
- Optional: `MT4_API_KEY`

Vercel checks:

- `https://YOUR_DOMAIN.vercel.app/`
- `https://YOUR_DOMAIN.vercel.app/api/health`
- `https://YOUR_DOMAIN.vercel.app/api/context/EURUSD`
- `https://YOUR_DOMAIN.vercel.app/api/?symbol=EURUSD`

MT4 should use the flat API URL for maximum compatibility:

- WebRequest allowlist: `https://YOUR_DOMAIN.vercel.app/api/`
- `DataApiUrl = https://YOUR_DOMAIN.vercel.app/api/`
- `BackupDataApiUrl =`
- `DataApiPath =`
- `UseFlatApiUrl = true`

Koyeb and Render guides exist, but Koyeb requested a deposit and Render requested payment in this workflow. Prefer Vercel unless the user chooses a paid host.

## Coding Style & Naming Conventions

Follow the existing style in each area:

- Frontend uses ES modules, React 18, double quotes, and semicolons.
- Backend uses Python with 4-space indentation, snake_case function names, and small module-level helpers.
- Keep UI text and comments in Spanish when extending existing user-facing frontend code.
- Preserve the current file layout unless a refactor is part of the task.

## Testing Guidelines

Automated tests are not set up yet. Before opening changes:

- Run `npm run build` for frontend changes when the environment allows it.
- For backend changes, run Python compile checks, start `uvicorn`, and verify `/health` plus one context endpoint such as `/context/EURUSD`.
- For Vercel routing changes, check both `/api/context/EURUSD` and `/context/EURUSD`.
- For MT4 changes, compile `atlas-data/examples/Atlas.mq4` in MetaEditor; this environment cannot compile MQL4.

Known environment limitation: this sandbox has previously blocked Vite/esbuild with `spawn EPERM`; do not treat that as conclusive project failure.

## MT4 EA Notes

Main EA:

- `atlas-data/examples/Atlas.mq4`

Important inputs:

- `UseDataApi = true`
- `RequireApiForTrading = true`
- `RequireTripleAlignment = true`
- `RequireLocalConfirmation = false`
- `CloseOnApiDisagreement = true`
- `ShowStatusPanel = true`
- `EmergencyStopPips = 25.0`
- `TrailingStartPips = 10.0`
- `TrailingStopPips = 8.0`
- `TrailingStepPips = 2.0`

The EA was copied into multiple local MetaTrader `MQL4\Experts` folders during the session, but future code changes still need recopying or manual replacement before MetaEditor compile.

## Commit & Pull Request Guidelines

Use short imperative commit subjects, for example:

- `Fix Vercel API routing`
- `Add MT4 triple alignment status panel`

Pull requests should include:

- A short description of what changed and why.
- Manual verification steps and affected commands.
- Screenshots for UI changes.
- Any new environment variables or API dependencies.

## Security & Configuration Tips

Do not commit secrets. Keep API keys in `atlas-data/.env` locally and in hosting environment variables for deployments.

Ignored local artifacts include:

- `node_modules/`
- `dist/`
- `.env`
- `atlas-data/.venv/`
- `atlas-data/.env`
- `atlas-data/cache.db*`
- `__pycache__/`
