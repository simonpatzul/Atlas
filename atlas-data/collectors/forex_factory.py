"""Calendario economico de Forex Factory (JSON no-oficial, libre)."""
from datetime import datetime, timezone

import httpx

import cache

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Mapeo divisa -> pares afectados de nuestro universo
PAIR_AFFECTED = {
    "USD": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD",
            "AUD/USD", "USD/CAD", "USD/CHF"],
    "EUR": ["EUR/USD"],
    "GBP": ["GBP/USD"],
    "JPY": ["USD/JPY"],
    "AUD": ["AUD/USD"],
    "CAD": ["USD/CAD"],
    "CHF": ["USD/CHF"],
}


async def fetch_calendar():
    cached = cache.get("ff_calendar")
    if cached is not None:
        return cached
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            URL, headers={"User-Agent": "Mozilla/5.0 atlas-data"}
        )
        r.raise_for_status()
        data = r.json()
    cache.put("ff_calendar", data, 1800)  # 30 min
    return data


def events_for_pair(events, pair, hours_ahead=24):
    now = datetime.now(timezone.utc)
    out = []
    for e in events:
        ccy = (e.get("currency") or e.get("country") or "").upper()
        if pair not in PAIR_AFFECTED.get(ccy, []):
            continue
        try:
            ts = datetime.fromisoformat(e["date"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts_utc = ts.astimezone(timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        delta_min = (ts_utc - now).total_seconds() / 60.0
        if delta_min < -15 or delta_min > hours_ahead * 60:
            continue
        out.append({
            "title": e.get("title"),
            "currency": ccy,
            "impact": e.get("impact", "Low"),
            "ts_utc": ts_utc.isoformat(),
            "minutes_until": round(delta_min, 1),
        })
    out.sort(key=lambda x: x["minutes_until"])
    return out
