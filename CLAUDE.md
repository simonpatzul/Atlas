# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

Two independently runnable sub-projects:

**Frontend** (`/` — Vite + React):
- `remixed-f545b974.tsx` — the only feature code. Self-contained React file (~50 KB, default export `AtlasChart`) with the prediction chart, indicators, and Monte Carlo overlay.
- `main.jsx` — mounts `AtlasChart` into `#root`.
- `index.html` — Vite entry, references `/main.jsx`.
- `vite.config.js` — `@vitejs/plugin-react`, dev server on port 5173 with `open: true`.
- `package.json` — React 18 + Vite 5. Scripts: `dev`, `build`, `preview`. No tests, no linter.

**Backend** (`atlas-data/` — Python FastAPI):
- `main.py` — FastAPI app on `http://127.0.0.1:8000`. Exposes market data, confluence context, and MT4-formatted signals for all 7 pairs.
- `engine.py` — assembles multi-source context: COT bias, macro/FRED trend, Alpha Vantage sentiment, Forex Factory news blocks.
- `scoring.py` — news risk level logic (high/medium impact event blocking).
- `collectors/` — one module per data source: `alpha.py` (Alpha Vantage sentiment), `cot.py` (CFTC COT), `fred.py` (FRED macro), `forex_factory.py` (economic calendar), `market.py` (live price snapshot).
- `config.py` — env-var driven config: `HOST`, `PORT`, `MT4_API_KEY`, `BLOCK_HIGH_IMPACT_MINUTES`, `BLOCK_MEDIUM_IMPACT_MINUTES`, `COT_BIAS_DIVISOR`.
- `cache.py` — SQLite-based caching (`cache.db`) used by collectors to avoid redundant API calls.
- `models.py` — Pydantic response models: `Mt4ContextResponse`, `DebugContextResponse`, `MarketSnapshotResponse`.
- `.env` / `.env.example` — requires `FRED_API_KEY` and `ALPHA_API_KEY`.

**README.md** — aspirational spec for ATLAS v5 (Spanish). References files and structure (`bridge/`, `config/`, `docs/`, etc.) that **do not exist outside `atlas-data/`**. Treat as design document, not current code.

Not present: TypeScript config (the `.tsx` file has no type annotations — Vite compiles it as JSX), tests, linter, git repo, MetaTrader bridge.

## Running it

**Frontend:**
```bash
npm install        # one-time
npm run dev        # http://localhost:5173, opens browser automatically
npm run build      # production bundle to dist/
npm run preview    # serve the built bundle
```

**Backend (`atlas-data/`):**
```bash
cd atlas-data
# Windows: double-click start.bat (creates venv, installs deps, starts uvicorn)
# Or manually:
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then fill in FRED_API_KEY and ALPHA_API_KEY
uvicorn main:app --host 127.0.0.1 --port 8000
```

Key endpoints: `GET /health`, `GET /context/{symbol}`, `GET /market/{symbol}`, `GET /mt4/context/{symbol}` (requires `x-api-key` header if `MT4_API_KEY` is set).

**Connecting frontend to backend:** set `VITE_ATLAS_API_BASE=http://127.0.0.1:8000` in a root-level `.env` before `npm run dev`. The frontend's `fetchJson()` function reads this at runtime; without it the frontend runs in fully static/offline mode using its hardcoded `BASE`/`CONFLUENCE` tables.

## The single source file

`remixed-f545b974.tsx` is `.tsx` by extension but contains **plain JSX with no TypeScript annotations**. It depends only on React (`useState`, `useEffect`, `useRef`, `useMemo`). Everything is in one file: data tables, math, sub-components, and the default export.

Internal layout (top to bottom):

1. **Static data**: `PAIRS`, `BASE` (price/vol/atr per pair), `CONFLUENCE` (per-pair score, bias, multi-TF RSI, COT). 7 supported pairs: EUR/USD, GBP/USD, USD/JPY, XAU/USD, AUD/USD, USD/CAD, USD/CHF.
2. **Format helpers**: `getDec(pair)` controls decimal precision (JPY → 2, XAU → 1, others → 4). All price formatting goes through `fmt(pair, value)`.
3. **Indicator math**: `calcEMA`, `calcBollinger`, `calcRSI`, `calcMACD`, `calcFibonacci`, `detectSR`. Pure functions over `closes[]` / `candles[]`.
4. **Monte Carlo engine**: `randn()` (Box-Muller) + `monteCarlo(pair, price, conf)` running 400 GBM paths over 12 steps. Returns `{stats, target, tp, tp2, sl, pips, conf, rr, bins, ...}` consumed by the chart.
5. **`calcTechScore`**: deterministic 0–100 score from EMA alignment, price vs EMA50, RSI, Bollinger position, MACD histogram, ROC(5). Returns `{score, signals[]}` where `signals[]` drives the on-screen breakdown.
6. **SVG sub-components**: `Chart`, `RSIChart`, `MACDChart`, `VolumeChart`, `DistChart` — all pure SVG, no external chart library.
7. **`AtlasChart`** (default export): orchestrates state, the live-price interval (1.6s tick), `predict()` which runs Monte Carlo and starts a 1-hour countdown, and the layout.

## Architectural conventions to preserve

These come from the README's "Convenciones importantes" section and match how the existing code is written:

- **Confluence/score thresholds are load-bearing**: `score >= 65` = bullish drift, `<= 35` = bearish, otherwise neutral. Score `>= 62` is the operate threshold; `>= 75` is "very strong". Keep these constants consistent if you add new scoring logic.
- **Final combined score is `confluence * 0.40 + technical * 0.60`** (see `combinedScore` in `AtlasChart`). Don't change the weighting without flagging it.
- **All indicators must be wrapped in `useMemo`** keyed on `closes` / `candles` — the live-price interval re-renders every 1.6s and recomputing per render will stutter.
- **Monte Carlo must stay deterministic-given-input**: the score → drift → path mapping is the contract the README documents. If you tweak `monteCarlo`, preserve the percentile semantics (`p5` = SL, `p50` = target, `p75` = TP, `p90` = TP2).
- **Decimal precision**: never hard-code `.toFixed(4)` — always route through `getDec(pair)` / `fmt(pair, v)` so JPY and XAU pairs render correctly.
- **Spanish in UI strings and comments** is the established style. Match it when extending.

## When the README and reality conflict

The README references files (`atlas-v5-complete.jsx`, `bridge/mt5_bridge.py`, `.env.example`, etc.) that don't exist. If a user asks you to "add a feature to ATLAS v5", first clarify whether they want you to:

1. Extend the existing `remixed-f545b974.tsx` (most likely — it's the only code), or
2. Scaffold the multi-file project layout the README describes (much larger task; needs explicit confirmation).

Don't silently create the README's file structure without asking.
