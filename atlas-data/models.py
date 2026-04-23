from typing import Literal

from pydantic import BaseModel


class ProviderStatus(BaseModel):
    ok: bool
    source: str
    detail: str


class TimeframeSignal(BaseModel):
    bias: Literal["UP", "DOWN", "NEUTRAL"]
    confidence: int
    score_adjust: int
    tradeable: bool
    summary: str


class SessionContext(BaseModel):
    code: str
    label: str
    is_london: bool
    is_ny: bool
    is_overlap: bool
    is_fix_window: bool


class EventBlock(BaseModel):
    active: bool
    reason: str | None = None
    blocked_until_utc: str | None = None
    minutes_to_unblock: float | None = None


class Mt4NewsEvent(BaseModel):
    title: str | None = None
    currency: str
    impact: str
    ts_utc: str
    minutes_until: float


class AdvancedModels(BaseModel):
    hurst_exponent: float
    hurst_regime: str
    linreg_slope_pct: float
    linreg_r2: float
    vol_regime: str
    tech_score_5m: float
    tech_score_15m: float
    tech_score_30m: float
    tech_score_1h: float
    tech_score_4h: float


class MarketCandle(BaseModel):
    ts_utc: str
    o: float
    h: float
    l: float
    c: float
    v: float


class MarketSnapshotResponse(BaseModel):
    symbol: str
    pair: str
    source: str
    ticker: str
    price: float
    previous_close: float
    change_pct: float
    last_updated: str
    day_open: float
    day_high: float
    day_low: float
    hour_high: float
    hour_low: float
    atr_14_pips: float
    realized_vol_pct: float
    candles: list[MarketCandle]


class Mt4ContextResponse(BaseModel):
    symbol: str
    pair: str
    ts_utc: str
    session: SessionContext
    event_block: EventBlock
    bias_5m: Literal["UP", "DOWN", "NEUTRAL"]
    bias_15m: Literal["UP", "DOWN", "NEUTRAL"]
    bias_30m: Literal["UP", "DOWN", "NEUTRAL"]
    bias_1h: Literal["UP", "DOWN", "NEUTRAL"]
    bias_4h: Literal["UP", "DOWN", "NEUTRAL"]
    bias_1d: Literal["UP", "DOWN", "NEUTRAL"]
    confidence_5m: int
    confidence_15m: int
    confidence_30m: int
    confidence_1h: int
    confidence_4h: int
    confidence_1d: int
    score_adjust_5m: int
    score_adjust_15m: int
    score_adjust_30m: int
    score_adjust_1h: int
    score_adjust_4h: int
    score_adjust_1d: int
    bias: Literal["UP", "DOWN", "NEUTRAL"]
    confidence: int
    expected_range_5m_pips: float
    expected_range_15m_pips: float
    expected_range_30m_pips: float
    expected_range_1h_pips: float
    expected_range_4h_pips: float
    expected_range_1d_pips: float
    invalidation_hint: str | None = None
    tradeable_5m: bool
    tradeable_15m: bool
    tradeable_30m: bool
    tradeable_1h: bool
    tradeable_4h: bool
    tradeable_1d: bool
    tradeable: bool
    news_risk: Literal["LOW", "MEDIUM", "HIGH"]
    next_event_minutes: float | None = None
    next_event_impact: str | None = None
    next_event_title: str | None = None
    macro_bias: float
    cot_bias: float
    sentiment_bias: float
    trend_bias: float
    score_adjust: int
    block_trading: bool
    block_reason: str | None = None
    news_surprise_boost: int = 0
    hurst_exponent: float = 0.5
    hurst_regime: str = "random"
    vol_regime: str = "NORMAL"
    tech_score_5m: float = 0.0
    tech_score_15m: float = 0.0
    tech_score_30m: float = 0.0
    tech_score_1h: float = 0.0
    tech_score_4h: float = 0.0
    providers: dict[str, ProviderStatus]


class DebugContextResponse(BaseModel):
    pair: str
    symbol: str
    ts_utc: str
    session: SessionContext
    event_block: EventBlock
    timeframe_5m: TimeframeSignal
    timeframe_15m: TimeframeSignal
    timeframe_30m: TimeframeSignal
    timeframe_1h: TimeframeSignal
    timeframe_4h: TimeframeSignal
    timeframe_1d: TimeframeSignal
    bias: Literal["UP", "DOWN", "NEUTRAL"]
    confidence: int
    expected_range_1h_pips: float
    invalidation_hint: str | None = None
    tradeable: bool
    news_risk: str
    news_penalty_pts: int
    next_event: Mt4NewsEvent | None = None
    events_24h: list[Mt4NewsEvent]
    cot: dict | None = None
    macro: dict
    sentiment: dict | None = None
    sentiment_bias: float
    cot_bias: float
    trend_bias: float
    score_adjust: int
    block_trading: bool
    block_reason: str | None = None
    advanced_models: AdvancedModels | None = None
    providers: dict[str, ProviderStatus]
