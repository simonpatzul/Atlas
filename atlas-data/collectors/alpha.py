"""AlphaVantage News Sentiment (free 25 req/day — cache agresiva)."""
import os

import httpx

import cache

URL = "https://www.alphavantage.co/query"

PAIR_TO_TICKER = {
    "EUR/USD": "FOREX:EUR",
    "GBP/USD": "FOREX:GBP",
    "USD/JPY": "FOREX:JPY",
    "XAU/USD": "FOREX:XAU",
    "AUD/USD": "FOREX:AUD",
    "USD/CAD": "FOREX:CAD",
    "USD/CHF": "FOREX:CHF",
}


async def fetch_sentiment(pair):
    key = os.getenv("ALPHA_API_KEY", "")
    if not key:
        return None
    cached = cache.get(f"alpha_{pair}")
    if cached is not None:
        return cached

    ticker = PAIR_TO_TICKER.get(pair)
    if not ticker:
        return None

    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "apikey": key,
        "limit": "20",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(URL, params=params)
        if r.status_code != 200:
            return None
        data = r.json()
    if data.get("Error Message"):
        raise RuntimeError(data["Error Message"])
    if data.get("Note"):
        raise RuntimeError("alpha_rate_limited")
    if data.get("Information"):
        raise RuntimeError(data["Information"])

    feed = data.get("feed", [])
    scores = []
    for art in feed[:20]:
        for ts in art.get("ticker_sentiment", []):
            if ts.get("ticker") == ticker:
                try:
                    scores.append(float(ts.get("ticker_sentiment_score", 0)))
                except (ValueError, TypeError):
                    pass

    if not scores:
        out = None
    else:
        out = {
            "avg_sentiment": round(sum(scores) / len(scores), 4),
            "n_articles": len(scores),
        }

    cache.put(f"alpha_{pair}", out, 3600)  # 1h
    return out
