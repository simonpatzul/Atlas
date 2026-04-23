"""CFTC Commitments of Traders (legacy futures) via Socrata API."""
import httpx

import cache

BASE = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

# Mercado CFTC -> (par, signo)
# signo = -1 si "long de especuladores" implica SHORT en el par USD/XXX
PAIR_MAP = {
    "EURO FX - CHICAGO MERCANTILE EXCHANGE":         ("EUR/USD", +1),
    "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE":   ("GBP/USD", +1),
    "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE":    ("USD/JPY", -1),
    "GOLD - COMMODITY EXCHANGE INC.":                ("XAU/USD", +1),
    "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE": ("AUD/USD", +1),
    "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE": ("USD/CAD", -1),
    "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE":     ("USD/CHF", -1),
}


async def fetch_cot():
    cached = cache.get("cot")
    if cached is not None:
        return cached

    where = " or ".join(
        [f"market_and_exchange_names='{n}'" for n in PAIR_MAP]
    )
    params = {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "200",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(BASE, params=params)
        r.raise_for_status()
        rows = r.json()

    out = {}
    for row in rows:
        name = row.get("market_and_exchange_names")
        if name not in PAIR_MAP:
            continue
        pair, sign = PAIR_MAP[name]
        if pair in out:  # ya tenemos la mas reciente (orden DESC)
            continue
        try:
            net = (
                int(row["noncomm_positions_long_all"])
                - int(row["noncomm_positions_short_all"])
            ) * sign
        except (KeyError, ValueError):
            continue
        out[pair] = {
            "cot_net": net,
            "report_date": row["report_date_as_yyyy_mm_dd"][:10],
        }

    cache.put("cot", out, 86400)  # 24h (publica viernes)
    return out
