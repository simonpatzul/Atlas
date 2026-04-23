import asyncio
import logging
from datetime import datetime, timedelta, timezone

from collectors import alpha, cot, forex_factory, fred, market
from config import (
    BLOCK_HIGH_IMPACT_MINUTES,
    BLOCK_MEDIUM_IMPACT_MINUTES,
    COT_BIAS_DIVISOR,
)
from models import (
    AdvancedModels,
    DebugContextResponse,
    EventBlock,
    Mt4ContextResponse,
    ProviderStatus,
    SessionContext,
    TimeframeSignal,
)
from scoring import news_risk_level

logger = logging.getLogger("atlas-data")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _sentiment_sign(pair: str) -> int:
    if pair in ("USD/JPY", "USD/CAD", "USD/CHF"):
        return -1
    return 1


def sentiment_bias_for_pair(pair: str, sent: dict | None) -> float:
    if not sent:
        return 0.0
    raw = float(sent.get("avg_sentiment", 0.0))
    return round(_clip(raw * _sentiment_sign(pair)), 3)


def cot_bias_for_pair(cot_data: dict | None) -> float:
    if not cot_data:
        return 0.0
    net = cot_data.get("cot_net")
    if net is None:
        return 0.0
    return round(_clip(float(net) / float(COT_BIAS_DIVISOR)), 3)


def trend_bias_for_pair(macro_bias: float, cot_bias: float, sentiment_bias: float) -> float:
    trend = macro_bias * 0.5 + cot_bias * 0.3 + sentiment_bias * 0.2
    return round(_clip(trend), 3)


def bias_from_trend(trend_bias: float, score_adjust: int) -> str:
    if trend_bias >= 0.12 or score_adjust >= 6:
        return "UP"
    if trend_bias <= -0.12 or score_adjust <= -6:
        return "DOWN"
    return "NEUTRAL"


def confidence_from_components(
    trend_bias: float,
    macro_bias: float,
    cot_bias: float,
    sentiment_bias: float,
    news_penalty: int,
) -> int:
    raw = (
        abs(trend_bias) * 45
        + abs(macro_bias) * 20
        + abs(cot_bias) * 15
        + abs(sentiment_bias) * 10
    )
    confidence = int(round(40 + raw - news_penalty * 0.6))
    return max(0, min(100, confidence))


def expected_range_1h_pips(pair: str, confidence: int, news_risk: str) -> float:
    base = {
        "EUR/USD": 10.0,
        "GBP/USD": 12.0,
        "USD/JPY": 11.0,
        "XAU/USD": 18.0,
        "AUD/USD": 9.0,
        "USD/CAD": 10.0,
        "USD/CHF": 9.0,
    }.get(pair, 10.0)
    conf_boost = (confidence - 50) * 0.08
    risk_boost = {"LOW": 0.0, "MEDIUM": 2.0, "HIGH": 4.0}.get(news_risk, 0.0)
    return round(max(4.0, base + conf_boost + risk_boost), 1)


def expected_range_for_horizon(horizon: str, pair: str, confidence: int, news_risk: str) -> float:
    base_1h = expected_range_1h_pips(pair, confidence, news_risk)
    multipliers = {
        "5m": 0.20,
        "15m": 0.38,
        "30m": 0.58,
        "1h": 1.0,
        "4h": 2.6,
        "1d": 6.0,
    }
    return round(max(1.0, base_1h * multipliers.get(horizon, 1.0)), 1)


def invalidation_hint_for_bias(bias: str) -> str | None:
    if bias == "UP":
        return "below_prev_hour_low"
    if bias == "DOWN":
        return "above_prev_hour_high"
    return None


def news_surprise_boost(recent_events: list[dict], pair: str) -> int:
    """
    Ajuste de score basado en sorpresas de noticias publicadas en la última hora.
    Positivo = alcista para el par, negativo = bajista.
    Lógica: sorpresa positiva en divisa base → alcista; en divisa cotizada → bajista.
    """
    if not recent_events or "/" not in pair:
        return 0
    base, quote = pair.split("/")
    boost = 0.0
    for e in recent_events:
        surprise = e.get("surprise")
        impact = (e.get("impact") or "").lower()
        currency = (e.get("currency") or "").upper()
        if surprise is None or surprise == 0:
            continue
        if currency == base:
            direction = 1.0
        elif currency == quote:
            direction = -1.0
        else:
            continue
        weight = {"high": 6.0, "medium": 3.0, "low": 1.0}.get(impact, 1.0)
        # Normalizar sorpresa: la mayoría < 1 unidad, cap en 3
        normalized = max(-1.0, min(1.0, surprise / 3.0))
        boost += direction * normalized * weight
    return max(-10, min(10, int(round(boost))))


def block_reason_for_event(event: dict | None) -> tuple[str | None, float | None]:
    if not event:
        return None, None
    impact = (event.get("impact") or "").lower()
    minutes = float(event.get("minutes_until", 99999))
    if impact == "high" and minutes <= BLOCK_HIGH_IMPACT_MINUTES:
        return f"high_impact_{int(round(minutes))}m", BLOCK_HIGH_IMPACT_MINUTES - minutes
    if impact == "medium" and minutes <= BLOCK_MEDIUM_IMPACT_MINUTES:
        return f"medium_impact_{int(round(minutes))}m", BLOCK_MEDIUM_IMPACT_MINUTES - minutes
    return None, None


def session_context(now: datetime | None = None) -> SessionContext:
    now = now or _now_utc()
    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute

    london_open = 7 * 60
    ny_open = 13 * 60
    ny_close = 21 * 60
    london_close = 16 * 60
    fix_start = 15 * 60 + 55
    fix_end = 16 * 60 + 5

    is_london = london_open <= total_minutes < london_close
    is_ny = ny_open <= total_minutes < ny_close
    is_overlap = ny_open <= total_minutes < london_close
    is_fix_window = fix_start <= total_minutes <= fix_end

    if is_fix_window:
        code = "LONDON_FIX"
        label = "London fix"
    elif is_overlap:
        code = "LONDON_NY"
        label = "Cruce Londres-Nueva York"
    elif is_london:
        code = "LONDON"
        label = "Sesión Londres"
    elif is_ny:
        code = "NEW_YORK"
        label = "Sesión Nueva York"
    else:
        code = "OFF_HOURS"
        label = "Fuera de sesión principal"

    return SessionContext(
        code=code,
        label=label,
        is_london=is_london,
        is_ny=is_ny,
        is_overlap=is_overlap,
        is_fix_window=is_fix_window,
    )


def timeframe_signal(
    horizon: str,
    *,
    macro_bias: float,
    cot_bias: float,
    sentiment_bias: float,
    trend_bias: float,
    news_penalty: int,
    risk_level: str,
    block_trading: bool,
    session: SessionContext,
    tech_score: float = 0.0,
) -> TimeframeSignal:
    """
    Calcula señal para un horizonte combinando fundamentales + score técnico de velas.
    tech_score: -1..+1 desde indicadores de precio (EMA, RSI, posición MA50).
    Pesos técnicos: 5m=70%, 15m=60%, 30m=50%, 1h=35%, 4h=20%, 1d=5%.
    """
    if horizon == "5m":
        blended = trend_bias * 0.30 + tech_score * 0.70
        score_adjust = round(blended * 8 + sentiment_bias * 3 - news_penalty * 1.3)
        if session.is_overlap:
            score_adjust += 2
        if session.is_fix_window:
            score_adjust -= 3
        confidence = max(0, min(100, int(round(
            28 + abs(tech_score) * 22 + abs(trend_bias) * 14 + abs(sentiment_bias) * 10 - news_penalty * 1.5
        ))))
        bias = bias_from_trend(blended, score_adjust)
        tradeable = (not block_trading) and bias != "NEUTRAL" and confidence >= 35 and risk_level != "HIGH"
        summary = "microstructure_momentum"

    elif horizon == "15m":
        blended = trend_bias * 0.40 + tech_score * 0.60
        score_adjust = round(blended * 9 + sentiment_bias * 4 - news_penalty * 1.1)
        if session.is_overlap:
            score_adjust += 2
        confidence = max(0, min(100, int(round(
            32 + abs(tech_score) * 20 + abs(trend_bias) * 16 + abs(sentiment_bias) * 8 - news_penalty * 1.3
        ))))
        bias = bias_from_trend(blended, score_adjust)
        tradeable = (not block_trading) and bias != "NEUTRAL" and confidence >= 38 and risk_level != "HIGH"
        summary = "short_momentum"

    elif horizon == "30m":
        blended = trend_bias * 0.50 + tech_score * 0.50
        score_adjust = round(blended * 10 + macro_bias * 5 + cot_bias * 3 - news_penalty * 0.9)
        if session.is_overlap:
            score_adjust += 2
        confidence = max(0, min(100, int(round(
            36 + abs(tech_score) * 16 + abs(trend_bias) * 16 + abs(macro_bias) * 8 - news_penalty * 1.0
        ))))
        bias = bias_from_trend(blended, score_adjust)
        tradeable = (not block_trading) and bias != "NEUTRAL" and confidence >= 42
        summary = "intraday_flow"

    elif horizon == "4h":
        blended = trend_bias * 0.80 + tech_score * 0.20
        score_adjust = round(macro_bias * 16 + cot_bias * 10 + blended * 8 - news_penalty * 0.5)
        confidence = max(0, min(100, int(round(
            42 + abs(macro_bias) * 22 + abs(cot_bias) * 14 + abs(tech_score) * 8 - news_penalty * 0.4
        ))))
        bias = bias_from_trend(blended, score_adjust)
        tradeable = bias != "NEUTRAL" and confidence >= 50
        summary = "session_swing"

    elif horizon == "1d":
        blended = trend_bias * 0.95 + tech_score * 0.05
        regime_bias = macro_bias * 0.60 + cot_bias * 0.30 + sentiment_bias * 0.10
        score_adjust = round(regime_bias * 20 + blended * 6 - news_penalty * 0.2)
        confidence = max(0, min(100, int(round(
            48 + abs(macro_bias) * 24 + abs(cot_bias) * 18 + abs(trend_bias) * 10
        ))))
        bias = bias_from_trend(regime_bias, score_adjust)
        tradeable = bias != "NEUTRAL" and confidence >= 55
        summary = "macro_regime"

    else:  # 1h (default)
        blended = trend_bias * 0.65 + tech_score * 0.35
        score_adjust = round(macro_bias * 14 + cot_bias * 8 + blended * 10 - news_penalty * 0.8)
        if session.is_overlap:
            score_adjust += 2
        confidence = max(0, min(100, int(round(
            confidence_from_components(trend_bias, macro_bias, cot_bias, sentiment_bias, news_penalty)
            + abs(tech_score) * 10
        ))))
        bias = bias_from_trend(blended, score_adjust)
        tradeable = (not block_trading) and bias != "NEUTRAL" and confidence >= 55
        summary = "rates_repricing"

    return TimeframeSignal(
        bias=bias,
        confidence=confidence,
        score_adjust=score_adjust,
        tradeable=tradeable,
        summary=summary,
    )


async def _safe_collect(name: str, source: str, coro, disabled_detail: str | None = None):
    try:
        data = await coro
        if data is None and disabled_detail:
            return None, ProviderStatus(ok=False, source=source, detail=disabled_detail)
        return data, ProviderStatus(ok=True, source=source, detail="ok")
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
        return None, ProviderStatus(ok=False, source=source, detail=str(exc))


async def collect_shared_inputs() -> dict:
    calendar_task = _safe_collect(
        "forex_factory",
        "Forex Factory",
        forex_factory.fetch_calendar(),
    )
    cot_task = _safe_collect(
        "cot",
        "CFTC COT",
        cot.fetch_cot(),
    )
    macro_task = _safe_collect(
        "fred",
        "FRED",
        fred.fetch_macro(),
        disabled_detail="disabled_no_fred_key",
    )
    (calendar_data, calendar_status), (cot_data, cot_status), (macro, macro_status) = (
        await asyncio.gather(calendar_task, cot_task, macro_task)
    )

    return {
        "calendar_data": calendar_data,
        "calendar_status": calendar_status,
        "cot_data": cot_data,
        "cot_status": cot_status,
        "macro": macro,
        "macro_status": macro_status,
    }


async def collect_sentiment_input(pair: str) -> tuple[dict | None, ProviderStatus]:
    return await _safe_collect(
        "alpha",
        "AlphaVantage",
        alpha.fetch_sentiment(pair),
        disabled_detail="disabled_no_alpha_key",
    )


def build_raw_context_from_inputs(
    sym: str,
    pair: str,
    shared_inputs: dict,
    sent: dict | None,
    sent_status: ProviderStatus,
    market_data: dict | None = None,
) -> dict:
    now = _now_utc()
    calendar_data = shared_inputs["calendar_data"]
    calendar_status = shared_inputs["calendar_status"]
    cot_data = shared_inputs["cot_data"]
    cot_status = shared_inputs["cot_status"]
    macro = shared_inputs["macro"]
    macro_status = shared_inputs["macro_status"]

    events = forex_factory.events_for_pair(calendar_data or [], pair, hours_ahead=24)
    recent_events = forex_factory.recent_events_for_pair(calendar_data or [], pair)
    risk_level, news_penalty = news_risk_level(events)
    next_event = events[0] if events else None
    surprise_boost = news_surprise_boost(recent_events, pair)

    # Análisis técnico desde velas (modelos avanzados)
    candles = (market_data or {}).get("candles") or []
    tech = market.candle_technicals(candles, sym)

    cot_pair = (cot_data or {}).get(pair)
    macro_bias = fred.macro_bias_for_pair(macro or {}, pair)
    sentiment_bias = sentiment_bias_for_pair(pair, sent)
    cot_bias = cot_bias_for_pair(cot_pair)
    trend_bias = trend_bias_for_pair(macro_bias, cot_bias, sentiment_bias)

    macro_pts = round(macro_bias * 10)
    sent_pts = round(sentiment_bias * 8)
    cot_pts = round(cot_bias * 6)
    trend_pts = round(trend_bias * 10)
    score_adjust = macro_pts + sent_pts + cot_pts + trend_pts - news_penalty + surprise_boost

    providers = {
        "calendar": calendar_status,
        "cot": cot_status,
        "macro": macro_status,
        "sentiment": sent_status,
    }

    block_reason, minutes_to_unblock = block_reason_for_event(next_event)
    block_trading = block_reason is not None
    blocked_until = (
        (now + timedelta(minutes=minutes_to_unblock)).isoformat()
        if minutes_to_unblock is not None
        else None
    )
    session = session_context(now)
    _tf_kwargs = dict(
        macro_bias=macro_bias,
        cot_bias=cot_bias,
        sentiment_bias=sentiment_bias,
        trend_bias=trend_bias,
        news_penalty=news_penalty,
        risk_level=risk_level,
        block_trading=block_trading,
        session=session,
    )
    tf_5m  = timeframe_signal("5m",  **_tf_kwargs, tech_score=tech["tech_5m"])
    tf_15m = timeframe_signal("15m", **_tf_kwargs, tech_score=tech["tech_15m"])
    tf_30m = timeframe_signal("30m", **_tf_kwargs, tech_score=tech["tech_30m"])
    tf_1h  = timeframe_signal("1h",  **_tf_kwargs, tech_score=tech["tech_1h"])
    tf_4h  = timeframe_signal("4h",  **_tf_kwargs, tech_score=tech["tech_4h"])
    tf_1d  = timeframe_signal("1d",  **_tf_kwargs, tech_score=0.0)

    bias = tf_1h.bias
    confidence = tf_1h.confidence
    expected_range_5m  = expected_range_for_horizon("5m",  pair, tf_5m.confidence,  risk_level)
    expected_range_15m = expected_range_for_horizon("15m", pair, tf_15m.confidence, risk_level)
    expected_range_30m = expected_range_for_horizon("30m", pair, tf_30m.confidence, risk_level)
    expected_range_1h  = expected_range_for_horizon("1h",  pair, tf_1h.confidence,  risk_level)
    expected_range_4h  = expected_range_for_horizon("4h",  pair, tf_4h.confidence,  risk_level)
    expected_range_1d  = expected_range_for_horizon("1d",  pair, tf_1d.confidence,  risk_level)
    invalidation_hint = invalidation_hint_for_bias(bias)
    tradeable = tf_1h.tradeable

    advanced_models = AdvancedModels(
        hurst_exponent=tech["hurst"],
        hurst_regime=tech["hurst_regime"],
        linreg_slope_pct=tech["linreg_slope_pct"],
        linreg_r2=tech["linreg_r2"],
        vol_regime=tech["vol_regime"],
        tech_score_5m=tech["tech_5m"],
        tech_score_15m=tech["tech_15m"],
        tech_score_30m=tech["tech_30m"],
        tech_score_1h=tech["tech_1h"],
        tech_score_4h=tech["tech_4h"],
    )

    return {
        "pair": pair,
        "symbol": sym,
        "ts_utc": now.isoformat(),
        "session": session,
        "event_block": EventBlock(
            active=block_trading,
            reason=block_reason,
            blocked_until_utc=blocked_until,
            minutes_to_unblock=round(minutes_to_unblock, 1) if minutes_to_unblock is not None else None,
        ),
        "timeframe_5m": tf_5m,
        "timeframe_15m": tf_15m,
        "timeframe_30m": tf_30m,
        "timeframe_1h": tf_1h,
        "timeframe_4h": tf_4h,
        "timeframe_1d": tf_1d,
        "bias_5m": tf_5m.bias,
        "bias_15m": tf_15m.bias,
        "bias_30m": tf_30m.bias,
        "bias_1h": tf_1h.bias,
        "bias_4h": tf_4h.bias,
        "bias_1d": tf_1d.bias,
        "confidence_5m": tf_5m.confidence,
        "confidence_15m": tf_15m.confidence,
        "confidence_30m": tf_30m.confidence,
        "confidence_1h": tf_1h.confidence,
        "confidence_4h": tf_4h.confidence,
        "confidence_1d": tf_1d.confidence,
        "score_adjust_5m": tf_5m.score_adjust,
        "score_adjust_15m": tf_15m.score_adjust,
        "score_adjust_30m": tf_30m.score_adjust,
        "score_adjust_1h": tf_1h.score_adjust,
        "score_adjust_4h": tf_4h.score_adjust,
        "score_adjust_1d": tf_1d.score_adjust,
        "bias": bias,
        "confidence": confidence,
        "expected_range_5m_pips": expected_range_5m,
        "expected_range_15m_pips": expected_range_15m,
        "expected_range_30m_pips": expected_range_30m,
        "expected_range_1h_pips": expected_range_1h,
        "expected_range_4h_pips": expected_range_4h,
        "expected_range_1d_pips": expected_range_1d,
        "invalidation_hint": invalidation_hint,
        "tradeable_5m": tf_5m.tradeable,
        "tradeable_15m": tf_15m.tradeable,
        "tradeable_30m": tf_30m.tradeable,
        "tradeable_1h": tf_1h.tradeable,
        "tradeable_4h": tf_4h.tradeable,
        "tradeable_1d": tf_1d.tradeable,
        "tradeable": tradeable,
        "news_risk": risk_level,
        "news_penalty_pts": news_penalty,
        "next_event": next_event,
        "events_24h": events,
        "cot": cot_pair,
        "macro": {
            "dxy_delta_pct": (macro or {}).get("dxy", {}).get("delta_pct"),
            "us10y_delta_pct": (macro or {}).get("us10y", {}).get("delta_pct"),
            "bias": round(macro_bias, 3),
            "bias_pts": macro_pts,
        },
        "sentiment": sent,
        "sentiment_bias": sentiment_bias,
        "sentiment_pts": sent_pts,
        "cot_bias": cot_bias,
        "trend_bias": trend_bias,
        "score_adjust": tf_1h.score_adjust,
        "block_trading": block_trading,
        "block_reason": block_reason,
        "news_surprise_boost": surprise_boost,
        "advanced_models": advanced_models,
        "providers": providers,
    }


async def build_raw_context(sym: str, pair: str) -> dict:
    shared_inputs, (sent, sent_status), (mkt, _mkt_status) = await asyncio.gather(
        collect_shared_inputs(),
        collect_sentiment_input(pair),
        _safe_collect("market", "Yahoo Finance", market.fetch_market(sym, pair)),
    )
    return build_raw_context_from_inputs(sym, pair, shared_inputs, sent, sent_status, mkt)


async def build_debug_context(sym: str, pair: str) -> DebugContextResponse:
    return DebugContextResponse(**(await build_raw_context(sym, pair)))


def _mt4_from_raw(sym: str, pair: str, raw: dict) -> Mt4ContextResponse:
    next_event = raw.get("next_event") or {}
    adv = raw.get("advanced_models")
    return Mt4ContextResponse(
        symbol=sym,
        pair=pair,
        ts_utc=raw["ts_utc"],
        session=raw["session"],
        event_block=raw["event_block"],
        bias_5m=raw["bias_5m"],
        bias_15m=raw["bias_15m"],
        bias_30m=raw["bias_30m"],
        bias_1h=raw["bias_1h"],
        bias_4h=raw["bias_4h"],
        bias_1d=raw["bias_1d"],
        confidence_5m=raw["confidence_5m"],
        confidence_15m=raw["confidence_15m"],
        confidence_30m=raw["confidence_30m"],
        confidence_1h=raw["confidence_1h"],
        confidence_4h=raw["confidence_4h"],
        confidence_1d=raw["confidence_1d"],
        score_adjust_5m=raw["score_adjust_5m"],
        score_adjust_15m=raw["score_adjust_15m"],
        score_adjust_30m=raw["score_adjust_30m"],
        score_adjust_1h=raw["score_adjust_1h"],
        score_adjust_4h=raw["score_adjust_4h"],
        score_adjust_1d=raw["score_adjust_1d"],
        bias=raw["bias"],
        confidence=raw["confidence"],
        expected_range_5m_pips=raw["expected_range_5m_pips"],
        expected_range_15m_pips=raw["expected_range_15m_pips"],
        expected_range_30m_pips=raw["expected_range_30m_pips"],
        expected_range_1h_pips=raw["expected_range_1h_pips"],
        expected_range_4h_pips=raw["expected_range_4h_pips"],
        expected_range_1d_pips=raw["expected_range_1d_pips"],
        invalidation_hint=raw["invalidation_hint"],
        tradeable_5m=raw["tradeable_5m"],
        tradeable_15m=raw["tradeable_15m"],
        tradeable_30m=raw["tradeable_30m"],
        tradeable_1h=raw["tradeable_1h"],
        tradeable_4h=raw["tradeable_4h"],
        tradeable_1d=raw["tradeable_1d"],
        tradeable=raw["tradeable"],
        news_risk=raw["news_risk"],
        next_event_minutes=next_event.get("minutes_until"),
        next_event_impact=next_event.get("impact"),
        next_event_title=next_event.get("title"),
        macro_bias=raw["macro"]["bias"],
        cot_bias=raw["cot_bias"],
        sentiment_bias=raw["sentiment_bias"],
        trend_bias=raw["trend_bias"],
        score_adjust=raw["score_adjust"],
        block_trading=raw["block_trading"],
        block_reason=raw["block_reason"],
        news_surprise_boost=raw.get("news_surprise_boost", 0),
        hurst_exponent=adv.hurst_exponent if adv else 0.5,
        hurst_regime=adv.hurst_regime if adv else "random",
        vol_regime=adv.vol_regime if adv else "NORMAL",
        tech_score_5m=adv.tech_score_5m if adv else 0.0,
        tech_score_15m=adv.tech_score_15m if adv else 0.0,
        tech_score_30m=adv.tech_score_30m if adv else 0.0,
        tech_score_1h=adv.tech_score_1h if adv else 0.0,
        tech_score_4h=adv.tech_score_4h if adv else 0.0,
        providers=raw["providers"],
    )


async def build_mt4_context(sym: str, pair: str) -> Mt4ContextResponse:
    raw = await build_raw_context(sym, pair)
    return _mt4_from_raw(sym, pair, raw)
