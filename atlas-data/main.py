"""ATLAS data API: contexto externo para consumir desde MT4."""
import asyncio
import logging
import os
from pathlib import Path
from time import time

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from collectors import market
from config import ALLOWED_HOSTS, CORS_ORIGINS, MT4_ALLOWED_API_KEYS
from engine import (
    _mt4_from_raw,
    build_debug_context,
    build_mt4_context,
    build_raw_context_from_inputs,
    collect_sentiment_input,
    collect_shared_inputs,
)
from models import DebugContextResponse, MarketSnapshotResponse, Mt4ContextResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

PAIRS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "XAUUSD": "XAU/USD",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
}

DASHBOARD = Path(__file__).parent / "dashboard.html"
STATIC_DIR = Path(os.getenv("ATLAS_STATIC_DIR", "")).resolve() if os.getenv("ATLAS_STATIC_DIR") else None

app = FastAPI(title="ATLAS data API", version="0.2.0")


def _default_cors_origins() -> list[str]:
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


def _default_allowed_hosts() -> list[str]:
    return [
        "localhost",
        "127.0.0.1",
        "*.vercel.app",
    ]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cache-Control"] = "no-store"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/" or path.startswith("/mt4/"):
            client = request.client.host if request.client else "unknown"
            now = time()
            bucket_start, count = self._buckets.get(client, (now, 0))
            if now - bucket_start >= self.window_seconds:
                bucket_start, count = now, 0
            count += 1
            self._buckets[client] = (bucket_start, count)
            if count > self.max_requests:
                return JSONResponse({"detail": "demasiadas solicitudes"}, status_code=429)
        return await call_next(request)


_cors_origins = list(CORS_ORIGINS) or _default_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["X-API-Key", "Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(ALLOWED_HOSTS) or _default_allowed_hosts(),
)

if STATIC_DIR and (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


def _normalize_symbol(symbol: str) -> tuple[str, str]:
    sym = symbol.upper().replace("/", "")
    pair = PAIRS.get(sym)
    if not pair:
        raise HTTPException(404, f"Simbolo no soportado: {sym}")
    return sym, pair


def _require_api_key(x_api_key: str | None):
    if MT4_ALLOWED_API_KEYS and x_api_key not in MT4_ALLOWED_API_KEYS:
        raise HTTPException(401, "x-api-key invalida")


@app.get("/", include_in_schema=False)
async def root(symbol: str | None = Query(default=None), x_api_key: str | None = Header(default=None)):
    if symbol:
        _require_api_key(x_api_key)
        sym, pair = _normalize_symbol(symbol)
        return await build_mt4_context(sym, pair)
    if STATIC_DIR and (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    return FileResponse(DASHBOARD)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "auth_enabled": bool(MT4_ALLOWED_API_KEYS),
        "pairs": sorted(PAIRS.keys()),
    }


@app.get("/context/{symbol}", response_model=DebugContextResponse)
async def context(symbol: str):
    sym, pair = _normalize_symbol(symbol)
    return await build_debug_context(sym, pair)


@app.get("/context-all", response_model=list[DebugContextResponse])
async def context_all():
    shared_inputs = await collect_shared_inputs()
    sentiment_results = await asyncio.gather(
        *[collect_sentiment_input(pair) for pair in PAIRS.values()]
    )
    results = [
        DebugContextResponse(
            **build_raw_context_from_inputs(sym, pair, shared_inputs, sent, sent_status)
        )
        for (sym, pair), (sent, sent_status) in zip(PAIRS.items(), sentiment_results, strict=False)
    ]
    return results


@app.get("/market/{symbol}", response_model=MarketSnapshotResponse)
async def market_snapshot(symbol: str):
    sym, pair = _normalize_symbol(symbol)
    return await market.fetch_market(sym, pair)


@app.get("/mt4/context/{symbol}", response_model=Mt4ContextResponse)
async def mt4_context(symbol: str, x_api_key: str | None = Header(default=None)):
    _require_api_key(x_api_key)
    sym, pair = _normalize_symbol(symbol)
    return await build_mt4_context(sym, pair)


@app.get("/mt4/context-all", response_model=list[Mt4ContextResponse])
async def mt4_context_all(x_api_key: str | None = Header(default=None)):
    _require_api_key(x_api_key)
    shared_inputs = await collect_shared_inputs()
    sentiment_results = await asyncio.gather(
        *[collect_sentiment_input(pair) for pair in PAIRS.values()]
    )
    results = []
    for (sym, pair), (sent, sent_status) in zip(PAIRS.items(), sentiment_results, strict=False):
        raw = build_raw_context_from_inputs(sym, pair, shared_inputs, sent, sent_status)
        results.append(_mt4_from_raw(sym, pair, raw))
    return results
