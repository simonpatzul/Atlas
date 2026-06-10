# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current State

ATLAS is a React + FastAPI trading context platform for FX/metals with MT4 integration.

Active surfaces:

- Frontend: root Vite/React app in `remixed-f545b974.tsx`, mounted by `main.jsx`.
- Backend: FastAPI service in `atlas-data/`.
- MT4 EAs: `atlas-data/examples/` (Atlas.mq4, AtlasBacktest.mq4, RutaV5AtlasAdaptiveLearner.mq4).
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

Vercel deployment is live at `https://atlas-delta-nine.vercel.app`. Frontend, backend API, and MT4 EA are all confirmed working.

## Backend

Main files:

- `atlas-data/main.py` — FastAPI app, endpoints, middleware (CORS, rate limit, security headers, trusted hosts)
- `atlas-data/engine.py` — context computation: `collect_shared_inputs()`, `timeframe_signal()`, `build_mt4_context()`
- `atlas-data/models.py` — Pydantic response models (Mt4ContextResponse, AdvancedModels, TimeframeSignal, etc.)
- `atlas-data/scoring.py` — `news_risk_level()`: classifies nearest event in 60m window as LOW/MEDIUM/HIGH
- `atlas-data/cache.py` — SQLite wrapper
- `atlas-data/config.py` — shared constants and settings
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

Multi-horizon context (6 timeframes):

- `timeframe_5m`, `timeframe_15m`, `timeframe_30m`, `timeframe_1h`, `timeframe_4h`, `timeframe_1d`
- MT4 fields: `bias_*`, `confidence_*`, `score_adjust_*`, `tradeable_*`, `expected_range_*_pips` para cada TF.
- Advanced models: `hurst_exponent`, `hurst_regime`, `linreg_slope_pct`, `linreg_r2`, `vol_regime`, `tech_score_*`.

Technical blending weights (tech vs fundamental):
- 5M: 70% tech / 30% fund
- 15M: 60% / 40%
- 30M: 50% / 50%
- 1H: 35% / 65%
- 4H: 20% / 80%
- 1D: 5% / 95%

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
- `MT4_API_KEY`: optional single-key auth for MT4 endpoints.
- `MT4_API_KEYS`: optional comma-separated list of valid keys (multi-client support).
- `ALLOWED_HOSTS`: comma-separated trusted hosts for `TrustedHostMiddleware` (default: `localhost,127.0.0.1`).

Environment variables:

```text
FRED_API_KEY=
ALPHA_API_KEY=
MT4_API_KEY=
MT4_API_KEYS=
CACHE_DB=/tmp/atlas-cache.db
CORS_ORIGINS=*
ALLOWED_HOSTS=localhost,127.0.0.1
BLOCK_HIGH_IMPACT_MINUTES=30
BLOCK_MEDIUM_IMPACT_MINUTES=15
COT_BIAS_DIVISOR=150000
```

Important robustness notes:

- `cache.py` defaults to `tempfile.gettempdir()/atlas-cache.db` (i.e. `/tmp/atlas-cache.db` on Linux/Vercel). The old default of `atlas-data/cache.db` caused `sqlite3.OperationalError` on Vercel's read-only Lambda filesystem. All cache ops are wrapped in try/except so DB failures degrade gracefully. `CACHE_DB` env var still overrides the path if needed.
- `market.py` now falls back to stale cache and then to a synthetic snapshot if Yahoo fails. This prevents frontend total failure from `/market/{symbol}`.
- Context collectors are wrapped with `_safe_collect` in `engine.py`; provider failures should degrade context, not crash the endpoint.
- Alpha Vantage rate limits should appear as provider failure, not app failure.
- `main.py` applies `SecurityHeadersMiddleware` (HSTS, X-Frame-Options, X-Content-Type-Options) and `RateLimitMiddleware` (60 req/min on `/` and `/mt4/*`). Both are in `main.py` as custom Starlette middleware classes.

## MT4 EAs

### Atlas.mq4 (main EA)

File: `atlas-data/examples/Atlas.mq4`

Strategy:

- Opens only when `bias_5m == bias_1h == bias_1d` and bias is `UP` or `DOWN`.
- Does not open on `NEUTRAL` or API/news block.
- Can close on API disagreement.
- Has emergency stop, trailing stop, and chart status panel.
- `AlignedCount()` requires ≥4/6 TFs aligned with `bias_1h` direction (6-way alignment).

### AtlasBacktest.mq4

File: `atlas-data/examples/AtlasBacktest.mq4`

Strategy Tester companion to Atlas.mq4. Simulates API context in backtests (no live WebRequest). Use in MetaTrader Strategy Tester to validate Atlas.mq4 logic historically.

### RutaV5AtlasAdaptiveLearner.mq4

File: `atlas-data/examples/RutaV5AtlasAdaptiveLearner.mq4`

RUTA v5 M1 Adaptive Learner — EURUSD mean reversion on M5 with M30 state filtering and M1 microstructure machine learning. Integrates the ATLAS API for macro confirmation.

Key design:
- **Entry**: Z-score mean reversion on M5 (default lookback=23, threshold=1.9), filtered by M30 state.
- **M1 Learner**: Adaptive Z-lookback (18), EMA fast/slow (4/11), entry score min (0.20). Activates after min 6 trades.
- **SL/TP**: ATR-based (initial 1.35×ATR, range 0.85–2.10), with swing lookback and emergency SL (2.80×ATR).
- **Session filter**: 6:00–22:00 UTC (London/NY overlap).
- **Risk**: configurable as % of balance (default 0.50%) or fixed lots.

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

For Vercel (valores por defecto actuales en el .mq4):

```text
DataApiUrl = https://atlas-delta-nine.vercel.app/api/
BackupDataApiUrl =
DataApiPath =
UseFlatApiUrl = true
```

MT4 WebRequest allowlist (Tools → Options → Expert Advisors):

```text
https://atlas-delta-nine.vercel.app/
```

Para desplegar el EA: copiar `atlas-data/examples/Atlas.mq4` a la carpeta `MQL4\Experts` de MetaTrader, compilar con F7 en MetaEditor y recargar en el gráfico. La ruta del usuario es `C:\Users\oscar\AppData\Roaming\MetaQuotes\Terminal\144726D86E6A9AA7C9A410DD1EA591F4\MQL4\Experts`.

El panel de estado muestra: API conectada/desconectada, último OK/fallo, pares alineados, sorpresa noticias, último error y configuración de riesgo.

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
ALLOWED_HOSTS=atlas-delta-nine.vercel.app
FRED_API_KEY=optional
ALPHA_API_KEY=optional
MT4_API_KEY=optional
MT4_API_KEYS=optional
```

Files used by Vercel:

- `vercel.json`: uses `version:2` with explicit `builds` + `routes`. **Do NOT use `rewrites`** — with rewrites, Vercel may pass the destination path (e.g., `/api/index`) into `scope["path"]` instead of the original request path, causing FastAPI to 404 on all routes. Explicit `routes` with `dest: "/api/index.py"` passes the original path correctly.
- `.python-version`: pins Python 3.12. The backend uses `str | None` syntax (Python 3.10+); Vercel's default Python 3.9 would silently fail to build the function.
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

If `/api/*` returns 404: verify `vercel.json` uses `builds`+`routes` (not `rewrites`), and that `.python-version` is `3.12`.

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
- **Vercel `/api` prefix**: `api/index.py` strips `/api` before forwarding to FastAPI; `vercel.json` uses `builds`+`routes` (not `rewrites`). If adding new routes, add the `src` pattern to `vercel.json` routes AND verify `api/index.py` strips the prefix correctly.
- **SQLite cache on Vercel**: `CACHE_DB` must point to `/tmp/atlas-cache.db` (writable path on Vercel serverless).
- **Market fallback chain**: `market.py` tries Yahoo → stale cache → synthetic snapshot, so the frontend never hard-fails on a market data outage.
- **News surprise boost**: `forex_factory.py` computes `actual - forecast` per recent event. `engine.py` aggregates into `news_surprise_boost` (-10..+10 pts) weighted by impact (HIGH=6, MED=3, LOW=1) and direction (base currency beats = positive, quote beats = negative). Added to `score_adjust` and exposed in `Mt4ContextResponse`. MT4 EA reads it from JSON and adds it to `combined` score, and displays it in the status panel as "Sorpresa noticias: +N".
- **Hurst Exponent**: R/S analysis on 5M closes. >0.6 = trending, <0.4 = mean-reverting. Computed in `market.py:hurst_exponent()`.
- **Linear Regression**: `market.py:linreg_slope_r2()` returns normalized slope and R² over 20 bars. Measures trend quality and direction.
- **Volatility Regime**: `market.py:vol_regime_from_candles()` classifies current ATR vs p25/p75 as LOW/NORMAL/HIGH.
- **Tech Score per TF**: `market.py:tech_score_from_candles()` returns -1..+1 from EMA9/21/50 stack (45%), RSI (30%), price-vs-MA50 (25%). Computed for 5M, 15M, 30M, 1H, 4H.
- **Per-TF tradeable confidence thresholds**: 5M≥35%, 15M≥38%, 30M≥42%, 1H≥55%, 4H≥50%, 1D≥55%. These differ by TF and must stay consistent between `engine.py:timeframe_signal()` and any frontend display logic.
- **6-way alignment in MT4 EA**: `AlignedCount()` counts how many of 6 TFs agree with bias_1h direction. Requires ≥4/6 aligned (was 3-way). Status panel shows Hurst and vol regime.
