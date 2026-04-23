"""FRED (St. Louis Fed) — DXY broad, 10y yield."""
import os

import httpx

import cache

BASE = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {"dxy": "DTWEXBGS", "us10y": "DGS10"}


async def _fetch_series(series_id):
    key = os.getenv("FRED_API_KEY", "")
    if not key:
        return None
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": "20",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(BASE, params=params)
        if r.status_code != 200:
            return None
        data = r.json()
    if data.get("error_code") or data.get("error_message"):
        raise RuntimeError(data.get("error_message") or "fred_error")
    return [
        float(o["value"])
        for o in data.get("observations", [])
        if o.get("value") not in (".", "", None)
    ]


async def fetch_macro():
    cached = cache.get("fred_macro")
    if cached is not None:
        return cached
    out = {}
    for k, sid in SERIES.items():
        vals = await _fetch_series(sid)
        if not vals or len(vals) < 6:
            continue
        latest = vals[0]
        avg5 = sum(vals[1:6]) / 5
        out[k] = {
            "latest": latest,
            "avg5d": avg5,
            "delta_pct": (latest - avg5) / avg5 * 100 if avg5 else 0.0,
        }
    cache.put("fred_macro", out, 3600)  # 1h
    return out


def macro_bias_for_pair(macro, pair):
    """Devuelve sesgo en [-1, +1] para la direccion del par."""
    if not macro:
        return 0.0
    dxy = macro.get("dxy", {}).get("delta_pct", 0.0)
    us10y = macro.get("us10y", {}).get("delta_pct", 0.0)

    # DXY arriba => USD fuerte
    if pair in ("EUR/USD", "GBP/USD", "AUD/USD", "XAU/USD"):
        bias = -dxy * 0.3
    else:
        bias = dxy * 0.3

    # US10Y afecta especialmente a USD/JPY
    if pair == "USD/JPY":
        bias += us10y * 0.4

    if bias > 1.0:
        return 1.0
    if bias < -1.0:
        return -1.0
    return bias
