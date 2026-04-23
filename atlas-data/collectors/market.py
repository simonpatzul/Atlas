"""Mercado spot/futures via Yahoo Finance chart API."""
from datetime import datetime, timedelta, timezone
from math import log, sqrt

import httpx

import cache

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

PAIR_TICKERS = {
    "EURUSD": ["EURUSD=X"],
    "GBPUSD": ["GBPUSD=X"],
    "USDJPY": ["JPY=X"],
    "XAUUSD": ["GC=F", "XAUUSD=X"],
    "AUDUSD": ["AUDUSD=X"],
    "USDCAD": ["CAD=X"],
    "USDCHF": ["CHF=X"],
}

FALLBACK_PRICE = {
    "EURUSD": 1.08,
    "GBPUSD": 1.26,
    "USDJPY": 155.0,
    "XAUUSD": 2350.0,
    "AUDUSD": 0.65,
    "USDCAD": 1.37,
    "USDCHF": 0.91,
}


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _pip_size(symbol: str) -> float:
    if symbol.endswith("JPY"):
        return 0.01
    if symbol == "XAUUSD":
        return 0.1
    return 0.0001


def _atr_14(candles: list[dict], symbol: str) -> float:
    if len(candles) < 15:
        return 0.0
    trs = []
    for idx in range(1, len(candles)):
        cur = candles[idx]
        prev_close = candles[idx - 1]["c"]
        tr = max(
            cur["h"] - cur["l"],
            abs(cur["h"] - prev_close),
            abs(cur["l"] - prev_close),
        )
        trs.append(tr)
    atr = sum(trs[-14:]) / 14
    return round(atr / _pip_size(symbol), 2)


def _realized_vol_pct(candles: list[dict]) -> float:
    if len(candles) < 20:
        return 0.0
    closes = [c["c"] for c in candles]
    returns = [log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return round(sqrt(variance) * 100, 4)


def _build_snapshot(symbol: str, pair: str, ticker: str, payload: dict) -> dict:
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError("market_no_result")

    result0 = result[0]
    meta = result0.get("meta") or {}
    quote_list = ((result0.get("indicators") or {}).get("quote") or [])
    if not quote_list:
        raise RuntimeError("market_no_quote")

    quote = quote_list[0]
    timestamps = result0.get("timestamp") or []
    candles = []
    for idx, ts in enumerate(timestamps):
        o = quote.get("open", [None])[idx]
        h = quote.get("high", [None])[idx]
        l = quote.get("low", [None])[idx]
        c = quote.get("close", [None])[idx]
        v = quote.get("volume", [0])[idx] or 0
        if None in (o, h, l, c):
            continue
        candles.append(
            {
                "ts_utc": _iso(ts),
                "o": round(float(o), 6),
                "h": round(float(h), 6),
                "l": round(float(l), 6),
                "c": round(float(c), 6),
                "v": float(v),
            }
        )

    if len(candles) < 30:
        raise RuntimeError("market_not_enough_candles")

    candles = candles[-60:]
    price = candles[-1]["c"]
    previous_close = meta.get("chartPreviousClose") or candles[-2]["c"]
    previous_close = float(previous_close)
    last_day = candles[-1]["ts_utc"][:10]
    day_candles = [c for c in candles if c["ts_utc"].startswith(last_day)]
    hour_candles = candles[-12:]

    return {
        "symbol": symbol,
        "pair": pair,
        "source": "Yahoo Finance",
        "ticker": ticker,
        "price": price,
        "previous_close": round(previous_close, 6),
        "change_pct": round(((price - previous_close) / previous_close) * 100, 4) if previous_close else 0.0,
        "last_updated": candles[-1]["ts_utc"],
        "day_open": day_candles[0]["o"],
        "day_high": max(c["h"] for c in day_candles),
        "day_low": min(c["l"] for c in day_candles),
        "hour_high": max(c["h"] for c in hour_candles),
        "hour_low": min(c["l"] for c in hour_candles),
        "atr_14_pips": _atr_14(candles, symbol),
        "realized_vol_pct": _realized_vol_pct(candles),
        "candles": candles,
    }


def _fallback_snapshot(symbol: str, pair: str, errors: list[str]) -> dict:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    base = FALLBACK_PRICE.get(symbol, 1.0)
    pip = _pip_size(symbol)
    candles = []
    for idx in range(60):
        ts = now - timedelta(minutes=(59 - idx) * 5)
        wave = ((idx % 12) - 6) * pip * 0.4
        drift = (idx - 30) * pip * 0.05
        close = base + wave + drift
        open_ = close - pip * 0.2
        high = max(open_, close) + pip * 1.5
        low = min(open_, close) - pip * 1.5
        candles.append(
            {
                "ts_utc": ts.isoformat(),
                "o": round(open_, 6),
                "h": round(high, 6),
                "l": round(low, 6),
                "c": round(close, 6),
                "v": 0.0,
            }
        )

    price = candles[-1]["c"]
    day_candles = candles
    hour_candles = candles[-12:]
    return {
        "symbol": symbol,
        "pair": pair,
        "source": "fallback_synthetic",
        "ticker": "fallback",
        "price": price,
        "previous_close": candles[-2]["c"],
        "change_pct": 0.0,
        "last_updated": candles[-1]["ts_utc"],
        "day_open": day_candles[0]["o"],
        "day_high": max(c["h"] for c in day_candles),
        "day_low": min(c["l"] for c in day_candles),
        "hour_high": max(c["h"] for c in hour_candles),
        "hour_low": min(c["l"] for c in hour_candles),
        "atr_14_pips": _atr_14(candles, symbol),
        "realized_vol_pct": _realized_vol_pct(candles),
        "candles": candles,
        "provider_errors": errors[-3:],
    }


async def fetch_market(symbol: str, pair: str) -> dict:
    cache_key = f"market_{symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    tickers = PAIR_TICKERS.get(symbol, [])
    if not tickers:
        raise RuntimeError(f"market_symbol_unsupported:{symbol}")

    params = {"interval": "5m", "range": "5d", "includePrePost": "false"}
    headers = {"User-Agent": "atlas-data/1.0"}
    errors = []
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for ticker in tickers:
            try:
                response = await client.get(URL.format(ticker=ticker), params=params)
                response.raise_for_status()
                out = _build_snapshot(symbol, pair, ticker, response.json())
                cache.put(cache_key, out, 60)
                return out
            except Exception as exc:
                errors.append(f"{ticker}:{exc}")

    stale = cache.get_stale(cache_key)
    if stale is not None:
        stale["source"] = f"{stale.get('source', 'cache')} (stale)"
        stale["provider_errors"] = errors[-3:]
        return stale

    return _fallback_snapshot(symbol, pair, errors)
