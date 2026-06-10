"""
Adaptive weight learner for ATLAS.

Tracks prediction outcomes (bias vs actual price move) and adjusts the
tech/fundamental blend weight per timeframe horizon over time.

Logic:
  - record_prediction(): saves a prediction when context is built
  - evaluate_with_candles(): on each market fetch, scores past predictions
    using the candle window (up to 10h history) and nudges weights
  - get_weight() / get_all_weights(): read current learned weights

The key insight: for each horizon, we track whether the TECHNICAL score
(EMA/RSI/ZScore/LinReg) or the FUNDAMENTAL blend (macro/COT/sentiment)
was better aligned with the actual price move. Whichever was more accurate
gets a higher weight in the next prediction.

Storage: shared SQLite DB (CACHE_DB / /tmp/atlas-cache.db).
"""
import logging
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Reuse the same SQLite file as cache.py (CACHE_DB env var or /tmp default)
DB = Path(os.getenv("CACHE_DB") or str(Path(tempfile.gettempdir()) / "atlas-cache.db"))

logger = logging.getLogger("atlas-learner")

# ── Default blend weights (must match engine.py base values) ──────────────
DEFAULTS: dict[str, float] = {
    "w_tech_5m":   0.70,
    "w_tech_15m":  0.60,
    "w_tech_30m":  0.50,
    "w_tech_1h":   0.35,
    "w_tech_4h":   0.20,
    "w_tech_1d":   0.05,
}

# Clamp to ±40% from default to prevent runaway adaptation
BOUNDS: dict[str, tuple[float, float]] = {
    k: (max(0.02, v * 0.60), min(0.98, v * 1.80))
    for k, v in DEFAULTS.items()
}

LR = 0.025                 # learning rate per outcome (≈2.5% weight change)
HORIZON_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
MIN_PIPS_MOVE = 2          # minimum price move in pips to score an outcome
RECORD_THROTTLE_FACTOR = 2 # only record a new prediction if last one is > horizon/2 old


def _conn():
    c = sqlite3.connect(str(DB), timeout=15, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("""
        CREATE TABLE IF NOT EXISTS learner_predictions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT    NOT NULL,
            horizon     TEXT    NOT NULL,
            ts_pred     REAL    NOT NULL,
            bias        TEXT    NOT NULL,
            confidence  INTEGER,
            entry_price REAL,
            tech_sign   INTEGER,  -- +1 tech bullish, -1 bearish, 0 neutral
            macro_sign  INTEGER,  -- +1 macro bullish, -1 bearish, 0 neutral
            evaluated   INTEGER DEFAULT 0,
            outcome     TEXT,     -- 'correct' | 'wrong' | 'insufficient_move'
            actual_price REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS learner_weights (
            key          TEXT  PRIMARY KEY,
            value        REAL  NOT NULL,
            n_updates    INTEGER DEFAULT 0,
            last_updated REAL
        )
    """)
    return c


# ── Public API ────────────────────────────────────────────────────────────

def get_weight(key: str) -> float:
    default = DEFAULTS.get(key, 0.5)
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT value FROM learner_weights WHERE key=?", (key,)
            ).fetchone()
        return row[0] if row else default
    except Exception as exc:
        logger.debug("learner.get_weight %s: %s", key, exc)
        return default


def get_all_weights() -> dict[str, float]:
    result = dict(DEFAULTS)
    try:
        with _conn() as c:
            for key, value in c.execute(
                "SELECT key, value FROM learner_weights"
            ).fetchall():
                if key in result:
                    result[key] = value
    except Exception as exc:
        logger.debug("learner.get_all_weights: %s", exc)
    return result


def record_prediction(
    symbol: str,
    horizon: str,
    bias: str,
    confidence: int,
    entry_price: float,
    tech_score: float,
    macro_bias: float,
) -> None:
    """
    Save a prediction for later evaluation. Throttled: skips if a prediction
    for this symbol+horizon was recorded within the last horizon/2 minutes.
    """
    if bias == "NEUTRAL" or entry_price <= 0 or horizon not in HORIZON_MINUTES:
        return
    throttle_sec = HORIZON_MINUTES[horizon] * 60 / RECORD_THROTTLE_FACTOR
    try:
        with _conn() as c:
            last = c.execute(
                "SELECT ts_pred FROM learner_predictions WHERE symbol=? AND horizon=? "
                "ORDER BY ts_pred DESC LIMIT 1",
                (symbol, horizon),
            ).fetchone()
            if last and time.time() - last[0] < throttle_sec:
                return
            c.execute(
                """INSERT INTO learner_predictions
                   (symbol, horizon, ts_pred, bias, confidence, entry_price, tech_sign, macro_sign)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol, horizon, time.time(), bias, confidence, entry_price,
                    _sign(tech_score, threshold=0.05),
                    _sign(macro_bias, threshold=0.05),
                ),
            )
    except Exception as exc:
        logger.debug("learner.record: %s", exc)


def evaluate_with_candles(
    symbol: str, candles: list[dict], pip_size: float = 0.0001
) -> None:
    """
    Evaluate pending predictions using the current candle window and update weights.
    Call once per market fetch for the same symbol.
    """
    if not candles:
        return

    price_map = _build_price_map(candles)
    if not price_map:
        return

    now = time.time()
    min_move = pip_size * MIN_PIPS_MOVE

    try:
        with _conn() as c:
            pending = c.execute(
                """SELECT id, horizon, ts_pred, bias, entry_price, tech_sign, macro_sign
                   FROM learner_predictions
                   WHERE symbol=? AND evaluated=0 AND ts_pred < ?
                   ORDER BY ts_pred ASC LIMIT 40""",
                (symbol, now),
            ).fetchall()
    except Exception as exc:
        logger.debug("learner.evaluate fetch: %s", exc)
        return

    for pred_id, horizon, ts_pred, bias, entry_price, tech_sign, macro_sign in pending:
        horizon_min = HORIZON_MINUTES.get(horizon, 60)
        target_ts = int(ts_pred + horizon_min * 60)

        if now < target_ts:
            continue  # not time yet

        actual = _lookup_price(price_map, target_ts, tolerance_sec=horizon_min * 90)
        if actual is None:
            continue  # no candle close enough

        move = actual - entry_price
        if abs(move) < min_move:
            outcome = "insufficient_move"
        elif (bias == "UP" and move > 0) or (bias == "DOWN" and move < 0):
            outcome = "correct"
        else:
            outcome = "wrong"

        try:
            with _conn() as c:
                c.execute(
                    "UPDATE learner_predictions SET evaluated=1, outcome=?, actual_price=? WHERE id=?",
                    (outcome, actual, pred_id),
                )
        except Exception as exc:
            logger.debug("learner.evaluate update: %s", exc)
            continue

        if outcome in ("correct", "wrong"):
            _update_weight(horizon, bias, outcome, tech_sign)


def get_stats() -> dict:
    """Returns current weights and prediction accuracy statistics."""
    try:
        with _conn() as c:
            w_rows = c.execute(
                "SELECT key, value, n_updates FROM learner_weights"
            ).fetchall()
            total = c.execute(
                "SELECT COUNT(*) FROM learner_predictions WHERE evaluated=1"
            ).fetchone()[0]
            correct = c.execute(
                "SELECT COUNT(*) FROM learner_predictions WHERE outcome='correct'"
            ).fetchone()[0]
            wrong = c.execute(
                "SELECT COUNT(*) FROM learner_predictions WHERE outcome='wrong'"
            ).fetchone()[0]
            pending = c.execute(
                "SELECT COUNT(*) FROM learner_predictions WHERE evaluated=0"
            ).fetchone()[0]
            by_h = c.execute(
                """SELECT horizon,
                       SUM(CASE WHEN outcome='correct' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN outcome='wrong'   THEN 1 ELSE 0 END)
                   FROM learner_predictions WHERE evaluated=1
                   GROUP BY horizon""",
            ).fetchall()

        w_map = {r[0]: {"value": round(r[1], 4), "n_updates": r[2]} for r in w_rows}
        horizon_stats = {
            h: {
                "correct": c_,
                "wrong": w_,
                "accuracy_pct": round(c_ / (c_ + w_) * 100, 1) if (c_ + w_) > 0 else None,
            }
            for h, c_, w_ in by_h
        }
        return {
            "weights": {
                k: w_map.get(k, {"value": DEFAULTS[k], "n_updates": 0})
                for k in DEFAULTS
            },
            "defaults": DEFAULTS,
            "total_evaluated": total,
            "correct": correct,
            "wrong": wrong,
            "accuracy_pct": round(correct / total * 100, 1) if total > 0 else None,
            "pending_evaluation": pending,
            "by_horizon": horizon_stats,
        }
    except Exception as exc:
        logger.debug("learner.get_stats: %s", exc)
        return {"weights": DEFAULTS, "total_evaluated": 0, "accuracy_pct": None}


# ── Internal helpers ──────────────────────────────────────────────────────

def _sign(value: float, threshold: float = 0.0) -> int:
    if value > threshold:
        return 1
    if value < -threshold:
        return -1
    return 0


def _build_price_map(candles: list[dict]) -> dict[int, float]:
    result: dict[int, float] = {}
    for bar in candles:
        try:
            ts_str = bar["ts_utc"].replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            result[int(dt.timestamp())] = bar["c"]
        except Exception:
            pass
    return result


def _lookup_price(
    price_map: dict[int, float], target_ts: int, tolerance_sec: int
) -> float | None:
    candidates = [
        (abs(t - target_ts), price)
        for t, price in price_map.items()
        if abs(t - target_ts) <= tolerance_sec
    ]
    if not candidates:
        return None
    _, price = min(candidates)
    return price


def _update_weight(horizon: str, bias: str, outcome: str, tech_sign: int) -> None:
    """
    Nudge w_tech_{horizon} based on whether the tech signal predicted correctly.

    Rule: tech_sign encodes the tech component's directional opinion at prediction time.
    If tech was pointing in the direction the price actually moved → tech was correct.
    Correct tech → increase w_tech. Incorrect tech → decrease w_tech.
    """
    key = f"w_tech_{horizon}"
    if key not in DEFAULTS or tech_sign == 0:
        return

    direction = 1 if bias == "UP" else -1
    # Actual price direction: correct means bias was right, wrong means opposite
    actual_direction = direction if outcome == "correct" else -direction
    tech_was_correct = (tech_sign == actual_direction)

    current = get_weight(key)
    lo, hi = BOUNDS[key]

    if tech_was_correct:
        new_val = min(hi, current * (1 + LR))
    else:
        new_val = max(lo, current * (1 - LR))

    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO learner_weights (key, value, n_updates, last_updated)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value        = excluded.value,
                       n_updates    = n_updates + 1,
                       last_updated = excluded.last_updated""",
                (key, round(new_val, 4), time.time()),
            )
        logger.debug(
            "learner weight %s: %.4f → %.4f (%s, tech_%s)",
            key, current, new_val, outcome, "correct" if tech_was_correct else "wrong",
        )
    except Exception as exc:
        logger.debug("learner._update_weight: %s", exc)
