# CLAUDE.md

This file gives Claude Code context for working on ATLAS.

## Current State

ATLAS is a React + FastAPI trading context platform for FX/metals with MT4 integration.

Active surfaces:

- Frontend: root Vite/React app in `remixed-f545b974.tsx`, mounted by `main.jsx`.
- Backend: FastAPI service in `atlas-data/`.
- MT4 EA: `atlas-data/examples/Atlas.mq4`.
- Vercel deployment adapter: `api/index.py`, `vercel.json`, root `requirements.txt`.

GitHub repo:

```text
https://github.com/simonpatzul/Atlas
```

## Frontend

Main file:

```text
remixed-f545b974.tsx
```

Important behavior:

- Supports prediction horizons `5M`, `1H`, and `1D`.
- Uses `PREDICTION_HORIZONS` to control countdown, Monte Carlo steps, and context layer.
- Fetches `/market/{symbol}` and `/context/{symbol}` through `fetchJson`.
- `API_BASE` is:
  - `VITE_ATLAS_API_BASE` when set.
  - `/api` automatically on `.vercel.app`.
  - empty locally, where Vite proxy handles backend routes.

Current Vercel issue history:

- The frontend originally called `/context/EURUSD` directly and Vercel returned 404.
- `vercel.json` now rewrites direct API-like paths and `/api/*`.
- `api/index.py` strips `/api` before handing requests to FastAPI.

## Backend

Main files:

- `atlas-data/main.py`
- `atlas-data/engine.py`
- `atlas-data/models.py`
- `atlas-data/cache.py`
- `atlas-data/collectors/*.py`

Important endpoints:

```text
GET /health
GET /context/{symbol}
GET /context-all
GET /market/{symbol}
GET /mt4/context/{symbol}
GET /mt4/context-all
GET /?symbol=EURUSD
```

The flat endpoint `/?symbol=EURUSD` returns MT4 context and is intended for MT4/WebRequest compatibility.

Multi-horizon context:

- `timeframe_5m`
- `timeframe_1h`
- `timeframe_1d`
- MT4 fields: `bias_5m`, `bias_1h`, `bias_1d`, `confidence_*`, `score_adjust_*`, `tradeable_*`, `expected_range_*_pips`.

Legacy fields `bias`, `confidence`, `score_adjust`, and `tradeable` map to the `1H` layer.

## External APIs

Collectors:

- `market.py`: Yahoo Finance chart API.
- `forex_factory.py`: Forex Factory/Fair Economy calendar JSON.
- `fred.py`: FRED macro data.
- `alpha.py`: Alpha Vantage news sentiment.
- `cot.py`: CFTC COT Socrata API.

Required/optional keys:

- `FRED_API_KEY`: optional but recommended for macro bias.
- `ALPHA_API_KEY`: optional; free tier is low-limit and may rate limit.
- `MT4_API_KEY`: optional security for MT4 endpoints.

Environment variables:

```text
FRED_API_KEY=
ALPHA_API_KEY=
MT4_API_KEY=
CACHE_DB=/tmp/atlas-cache.db
CORS_ORIGINS=*
BLOCK_HIGH_IMPACT_MINUTES=30
BLOCK_MEDIUM_IMPACT_MINUTES=15
COT_BIAS_DIVISOR=150000
```

Important robustness notes:

- `cache.py` must use `CACHE_DB`; on Vercel this should be `/tmp/atlas-cache.db`.
- `market.py` now falls back to stale cache and then to a synthetic snapshot if Yahoo fails. This prevents frontend total failure from `/market/{symbol}`.
- Context collectors are wrapped with `_safe_collect` in `engine.py`; provider failures should degrade context, not crash the endpoint.
- Alpha Vantage rate limits should appear as provider failure, not app failure.

## MT4 EA

Main file:

```text
atlas-data/examples/Atlas.mq4
```

Current strategy:

- Opens only when `bias_5m == bias_1h == bias_1d` and bias is `UP` or `DOWN`.
- Does not open on `NEUTRAL` or API/news block.
- Can close on API disagreement.
- Has emergency stop, trailing stop, and chart status panel.

Important inputs:

```text
UseDataApi = true
RequireApiForTrading = true
RequireTripleAlignment = true
RequireLocalConfirmation = false
CloseOnApiDisagreement = true
ShowStatusPanel = true
EmergencyStopPips = 25.0
TrailingStartPips = 10.0
TrailingStopPips = 8.0
TrailingStepPips = 2.0
UseFlatApiUrl = true
```

For Vercel:

```text
DataApiUrl = https://YOUR_DOMAIN.vercel.app/api/
BackupDataApiUrl =
DataApiPath =
UseFlatApiUrl = true
```

MT4 WebRequest allowlist:

```text
https://YOUR_DOMAIN.vercel.app/api/
```

The EA status panel should show whether the API is connected, last OK/failure time, aligned pair count, last error, and risk settings.

## Vercel Deployment

Vercel is the current preferred free deployment target.

Settings:

```text
Root Directory: ./
Framework Preset: Vite
Build Command: npm run build
Output Directory: dist
```

Environment variables:

```text
VITE_ATLAS_API_BASE=/api
CORS_ORIGINS=*
CACHE_DB=/tmp/atlas-cache.db
FRED_API_KEY=optional
ALPHA_API_KEY=optional
MT4_API_KEY=optional
```

Files used by Vercel:

- `vercel.json`: declares `python3.12` runtime for `api/index.py` and rewrites all `/api/*` traffic to that function. **Python runtime must be specified explicitly** — the backend uses `str | None` union syntax (Python 3.10+) which fails silently on Vercel's default Python 3.9, causing every `/api/*` request to 404.
- `api/index.py`: imports FastAPI app and strips `/api` prefix from `scope["path"]` before forwarding to the ASGI app.
- root `requirements.txt`: must list dependencies explicitly. Do not use `-r atlas-data/requirements.txt`.

Useful Vercel checks:

```text
https://YOUR_DOMAIN.vercel.app/
https://YOUR_DOMAIN.vercel.app/api/health
https://YOUR_DOMAIN.vercel.app/api/context/EURUSD
https://YOUR_DOMAIN.vercel.app/api/market/EURUSD
https://YOUR_DOMAIN.vercel.app/api/?symbol=EURUSD
```

If `/api/*` returns 404: first check that `vercel.json` has `"functions": { "api/index.py": { "runtime": "python3.12" } }`. A missing or wrong Python version means the function never builds.

## Local Development

Frontend:

```powershell
cd C:\Users\oscar\Documents\Claude
cmd /c npm run dev
```

Backend:

```powershell
cd C:\Users\oscar\Documents\Claude\atlas-data
.\.venv\Scripts\activate
uvicorn main:app --host 127.0.0.1 --port 8000
```

Checks:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/context/EURUSD
http://127.0.0.1:8000/market/EURUSD
http://127.0.0.1:8000/?symbol=EURUSD
```

`atlas-launch.bat` starts backend, frontend, and browser locally.

## Verification

No automated tests are configured.

Use:

```powershell
cd atlas-data
.\.venv\Scripts\python.exe -m py_compile main.py engine.py models.py scoring.py cache.py collectors\market.py collectors\forex_factory.py collectors\fred.py collectors\alpha.py collectors\cot.py
```

For Vercel wrapper:

```powershell
.\atlas-data\.venv\Scripts\python.exe -m py_compile api\index.py
```

For frontend:

```powershell
cmd /c npm run build
```

Known limitation: this local Codex sandbox previously failed Vite/esbuild with `spawn EPERM`; Vercel build has succeeded before.

## Style Rules

- Frontend uses ES modules, React 18, double quotes, and semicolons.
- Backend uses Python 4-space indentation and snake_case.
- Keep user-facing UI text in Spanish.
- Do not commit secrets or local `.env`.
- Do not commit `node_modules`, `.venv`, `dist`, `cache.db`, or `__pycache__`.

## Architectural Invariants

These are load-bearing constraints — don't change without flagging:

- **Score thresholds**: `score >= 65` = bullish drift, `<= 35` = bearish, otherwise neutral. `>= 62` = operate threshold; `>= 75` = "very strong". Keep consistent across frontend and backend scoring logic.
- **Combined score weighting**: `confluence * 0.40 + technical * 0.60` (see `combinedScore` in `AtlasChart`).
- **`useMemo` on all indicators**: the 1.6s live-price interval re-renders constantly — any indicator not memoized on `closes`/`candles` will stutter.
- **Monte Carlo percentile semantics**: `p5` = SL, `p50` = target, `p75` = TP, `p90` = TP2. Preserve these if tweaking `monteCarlo()`.
- **Decimal precision**: always route through `getDec(pair)` / `fmt(pair, v)` — never hardcode `.toFixed(4)` (breaks JPY and XAU).
- **Vercel `/api` prefix**: `api/index.py` strips `/api` before forwarding to FastAPI; `vercel.json` rewrites both direct API paths and `/api/*`. If adding new routes, verify both files.
- **SQLite cache on Vercel**: `CACHE_DB` must point to `/tmp/atlas-cache.db` (writable path on Vercel serverless).
- **Market fallback chain**: `market.py` tries Yahoo → stale cache → synthetic snapshot, so the frontend never hard-fails on a market data outage.
