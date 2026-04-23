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


def aggregate_candles(candles: list[dict], n: int) -> list[dict]:
    """Agrupa n velas M5 consecutivas en una barra de mayor timeframe."""
    out = []
    for i in range(0, len(candles) - n + 1, n):
        g = candles[i : i + n]
        out.append({
            "ts_utc": g[0]["ts_utc"],
            "o": g[0]["o"],
            "h": max(c["h"] for c in g),
            "l": min(c["l"] for c in g),
            "c": g[-1]["c"],
            "v": sum(c["v"] for c in g),
        })
    return out


def _ema_series(closes: list[float], period: int) -> list[float]:
    if len(closes) < period:
        return []
    k = 2.0 / (period + 1)
    result = [sum(closes[:period]) / period]
    for c in closes[period:]:
        result.append(c * k + result[-1] * (1 - k))
    return result


def _rsi_value(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    avg_g = sum(max(0.0, d) for d in recent) / period
    avg_l = sum(max(0.0, -d) for d in recent) / period
    if avg_l == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_g / avg_l), 2)


def tech_score_from_candles(candles: list[dict]) -> float:
    """
    Score técnico -1..+1 basado en alineación EMA, RSI y posición vs MA50.
    Requiere mínimo 52 velas.
    """
    if len(candles) < 52:
        return 0.0
    closes = [c["c"] for c in candles]
    e9 = _ema_series(closes, 9)
    e21 = _ema_series(closes, 21)
    e50 = _ema_series(closes, 50)
    if not (e9 and e21 and e50):
        return 0.0
    price, v9, v21, v50 = closes[-1], e9[-1], e21[-1], e50[-1]

    if v9 > v21 > v50:
        stack = 1.0
    elif v9 < v21 < v50:
        stack = -1.0
    else:
        stack = 0.35 * (1 if v9 > v21 else -1)

    rsi_v = _rsi_value(closes)
    if rsi_v is None:
        rsi_sig = 0.0
    elif rsi_v > 70:
        rsi_sig = -0.8
    elif rsi_v < 30:
        rsi_sig = 0.8
    elif rsi_v > 55:
        rsi_sig = 0.4
    elif rsi_v < 45:
        rsi_sig = -0.4
    else:
        rsi_sig = 0.0

    pct = (price - v50) / v50 if v50 else 0.0
    ma_sig = max(-1.0, min(1.0, pct * 150))

    score = stack * 0.45 + rsi_sig * 0.30 + ma_sig * 0.25
    return round(max(-1.0, min(1.0, score)), 4)


def hurst_exponent(closes: list[float]) -> float:
    """
    Exponente de Hurst via R/S analysis.
    >0.6 = tendencia persistente, 0.4-0.6 = paseo aleatorio, <0.4 = reversión a la media.
    """
    n = len(closes)
    if n < 20:
        return 0.5
    lags = [l for l in [4, 8, 16, 32, 64] if l < n]
    log_rs, log_lags = [], []
    for lag in lags:
        rs_list = []
        for start in range(0, n - lag, lag):
            chunk = closes[start : start + lag]
            if len(chunk) < lag:
                continue
            mean = sum(chunk) / lag
            devs = [c - mean for c in chunk]
            cum, cumdevs = 0.0, []
            for d in devs:
                cum += d
                cumdevs.append(cum)
            R = max(cumdevs) - min(cumdevs)
            S = sqrt(sum(d * d for d in devs) / lag)
            if S > 0:
                rs_list.append(R / S)
        if rs_list:
            log_rs.append(log(sum(rs_list) / len(rs_list)))
            log_lags.append(log(lag))
    if len(log_rs) < 2:
        return 0.5
    lx = sum(log_lags) / len(log_lags)
    ly = sum(log_rs) / len(log_rs)
    num = sum((log_lags[i] - lx) * (log_rs[i] - ly) for i in range(len(log_lags)))
    den = sum((v - lx) ** 2 for v in log_lags)
    return round(num / den, 3) if den else 0.5


def linreg_slope_r2(closes: list[float], period: int = 20) -> tuple[float, float]:
    """Regresión lineal sobre las últimas `period` velas. Devuelve (slope_pct_por_barra, r²)."""
    if len(closes) < period:
        return 0.0, 0.0
    y = closes[-period:]
    n = period
    xm = (n - 1) / 2.0
    ym = sum(y) / n
    xy = sum((i - xm) * (y[i] - ym) for i in range(n))
    xx = sum((i - xm) ** 2 for i in range(n))
    yy = sum((v - ym) ** 2 for v in y)
    if xx == 0:
        return 0.0, 0.0
    slope = xy / xx
    r2 = (xy * xy) / (xx * yy) if yy else 0.0
    slope_pct = slope / ym * 100 if ym else 0.0
    return round(slope_pct, 6), round(r2, 4)


def vol_regime_from_candles(candles: list[dict], symbol: str) -> str:
    """Clasifica la volatilidad actual como LOW, NORMAL o HIGH vs ATR histórico."""
    if len(candles) < 20:
        return "NORMAL"
    pip = _pip_size(symbol)
    trs = []
    for idx in range(1, len(candles)):
        tr = max(
            candles[idx]["h"] - candles[idx]["l"],
            abs(candles[idx]["h"] - candles[idx - 1]["c"]),
            abs(candles[idx]["l"] - candles[idx - 1]["c"]),
        )
        trs.append(tr / pip if pip else tr)
    current = sum(trs[-14:]) / 14
    hist = sorted(trs)
    p25 = hist[len(hist) // 4]
    p75 = hist[3 * len(hist) // 4]
    if current > p75 * 1.3:
        return "HIGH"
    if current < p25 * 0.8:
        return "LOW"
    return "NORMAL"


def candle_technicals(candles: list[dict], symbol: str) -> dict:
    """
    Calcula todos los indicadores técnicos desde velas M5.
    Devuelve scores por timeframe y modelos avanzados (Hurst, LinReg, VolRegime).
    """
    empty = {
        "tech_5m": 0.0, "tech_15m": 0.0, "tech_30m": 0.0,
        "tech_1h": 0.0, "tech_4h": 0.0,
        "hurst": 0.5, "hurst_regime": "random",
        "linreg_slope_pct": 0.0, "linreg_r2": 0.0,
        "vol_regime": "NORMAL",
    }
    if not candles:
        return empty

    bars_15m = aggregate_candles(candles, 3)
    bars_30m = aggregate_candles(candles, 6)
    bars_1h = aggregate_candles(candles, 12)
    bars_4h = aggregate_candles(candles, 48)

    closes = [c["c"] for c in candles]
    h = hurst_exponent(closes)
    slope, r2 = linreg_slope_r2(closes)

    return {
        "tech_5m": tech_score_from_candles(candles),
        "tech_15m": tech_score_from_candles(bars_15m),
        "tech_30m": tech_score_from_candles(bars_30m),
        "tech_1h": tech_score_from_candles(bars_1h),
        "tech_4h": tech_score_from_candles(bars_4h),
        "hurst": h,
        "hurst_regime": "trending" if h > 0.6 else ("mean_reverting" if h < 0.4 else "random"),
        "linreg_slope_pct": slope,
        "linreg_r2": r2,
        "vol_regime": vol_regime_from_candles(candles, symbol),
    }


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
