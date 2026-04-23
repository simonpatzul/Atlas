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


def _parse_num(s: str | None) -> float | None:
    """Convierte strings como '3.2%', '-0.1', '125K' a float. None si no parseable."""
    if not s or s.strip() in ("", "N/A", "—", "-"):
        return None
    s = s.strip().replace("%", "").replace(",", "")
    s = s.replace("K", "e3").replace("M", "e6").replace("B", "e9")
    try:
        return float(s)
    except ValueError:
        return None


def _calc_surprise(actual_str: str | None, forecast_str: str | None) -> float | None:
    """Sorpresa = actual - forecast. None si alguno no disponible."""
    actual = _parse_num(actual_str)
    forecast = _parse_num(forecast_str)
    if actual is None or forecast is None:
        return None
    return round(actual - forecast, 4)


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


def _build_event(e: dict, ccy: str, ts_utc: datetime, delta_min: float) -> dict:
    actual_str = e.get("actual")
    forecast_str = e.get("forecast")
    return {
        "title": e.get("title"),
        "currency": ccy,
        "impact": e.get("impact", "Low"),
        "ts_utc": ts_utc.isoformat(),
        "minutes_until": round(delta_min, 1),
        "actual": actual_str,
        "forecast": forecast_str,
        "previous": e.get("previous"),
        "surprise": _calc_surprise(actual_str, forecast_str),
    }


def _iter_pair_events(events, pair):
    """Itera eventos del calendario que afectan al par, con timestamps parseados."""
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
        yield e, ccy, ts_utc


def events_for_pair(events, pair, hours_ahead=24):
    """Eventos próximos (hasta -15 min pasados) para bloqueo y próximo evento."""
    now = datetime.now(timezone.utc)
    out = []
    for e, ccy, ts_utc in _iter_pair_events(events, pair):
        delta_min = (ts_utc - now).total_seconds() / 60.0
        if delta_min < -15 or delta_min > hours_ahead * 60:
            continue
        out.append(_build_event(e, ccy, ts_utc, delta_min))
    out.sort(key=lambda x: x["minutes_until"])
    return out


def recent_events_for_pair(events, pair, lookback_minutes=60):
    """Eventos publicados en los últimos lookback_minutes para calcular sorpresa."""
    now = datetime.now(timezone.utc)
    out = []
    for e, ccy, ts_utc in _iter_pair_events(events, pair):
        delta_min = (ts_utc - now).total_seconds() / 60.0
        if not (-lookback_minutes <= delta_min <= 2):
            continue
        out.append(_build_event(e, ccy, ts_utc, delta_min))
    out.sort(key=lambda x: x["minutes_until"])
    return out
