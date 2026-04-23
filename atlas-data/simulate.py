#!/usr/bin/env python3
"""
ATLAS Backtest Simulator
Simula señales técnicas de 6 timeframes en datos históricos 5M y calcula
métricas de rendimiento: win rate, profit factor, Sharpe, Sortino,
max drawdown, expectancy, y desglose por par.
"""

import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))

from collectors.market import _atr_14, _pip_size, aggregate_candles, tech_score_from_candles

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD", "USDCHF"]

TICKERS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",    "XAUUSD": "GC=F",
    "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X",
    "USDCHF": "CHF=X",
}

SPREAD_PIPS = {
    "EURUSD": 1.5, "GBPUSD": 2.0, "USDJPY": 1.5,
    "XAUUSD": 4.0, "AUDUSD": 2.0, "USDCAD": 2.0, "USDCHF": 2.0,
}

WARMUP_BARS   = 3000  # 3000 M5 = ~62 H4 bars para EMA50 H4
ATR_SL_MULT   = 2.0   # SL = ATR * 2
ATR_TP_MULT   = 3.0   # TP = ATR * 3 -> RR 1.5
COUNTDOWN_BARS = 12   # salida por tiempo: 12 velas M5 = 1H
MIN_ALIGNED   = 3     # timeframes mínimos alineados de 6
BIAS_THRESH   = 0.12  # score mínimo para ser direccional

# ---------------------------------------------------------------------------
# Descarga de datos
# ---------------------------------------------------------------------------
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


def fetch_candles(symbol: str) -> list[dict]:
    ticker = TICKERS[symbol]
    params = {"interval": "5m", "range": "60d", "includePrePost": "false"}
    headers = {"User-Agent": "Mozilla/5.0 atlas-backtest/1.0"}
    for attempt in range(3):
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(YAHOO_URL.format(ticker=ticker), params=params, headers=headers)
                r.raise_for_status()
                data = r.json()
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < 2:
                time.sleep(8 + attempt * 5)
                continue
            raise
    result = ((data.get("chart") or {}).get("result") or [])
    if not result:
        return []
    r0 = result[0]
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    timestamps = r0.get("timestamp") or []
    candles = []
    for i, ts in enumerate(timestamps):
        o = (quote.get("open")  or [None])[i]
        h = (quote.get("high")  or [None])[i]
        l = (quote.get("low")   or [None])[i]
        c = (quote.get("close") or [None])[i]
        if None in (o, h, l, c):
            continue
        from datetime import datetime, timezone
        ts_iso = datetime.fromtimestamp(ts, timezone.utc).isoformat()
        candles.append({"ts_utc": ts_iso, "ts": ts, "o": float(o),
                         "h": float(h), "l": float(l), "c": float(c), "v": 0.0})
    return candles


# ---------------------------------------------------------------------------
# Generación de señal (6 TF)
# ---------------------------------------------------------------------------
def compute_signal(candles: list[dict]) -> str:
    """UP / DOWN / NEUTRAL según alineación de ≥4 de 6 timeframes."""
    scores = [
        tech_score_from_candles(candles),                   # M5
        tech_score_from_candles(aggregate_candles(candles, 3)),   # M15
        tech_score_from_candles(aggregate_candles(candles, 6)),   # M30
        tech_score_from_candles(aggregate_candles(candles, 12)),  # H1
        tech_score_from_candles(aggregate_candles(candles, 48)),  # H4
        tech_score_from_candles(aggregate_candles(candles, 12)),  # D1 proxy (H1 trend)
    ]
    biases = [
        "UP" if s > BIAS_THRESH else ("DOWN" if s < -BIAS_THRESH else "NEUTRAL")
        for s in scores
    ]
    up   = biases.count("UP")
    down = biases.count("DOWN")
    if up >= MIN_ALIGNED:
        return "UP"
    if down >= MIN_ALIGNED:
        return "DOWN"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Simulación de operaciones
# ---------------------------------------------------------------------------
class Trade:
    def __init__(self, direction, entry, sl, tp, entry_bar, pip_size, spread_pips):
        self.direction  = direction
        self.entry      = entry
        self.sl         = sl
        self.tp         = tp
        self.entry_bar  = entry_bar
        self.pip_size   = pip_size
        self.spread     = spread_pips

    def check_exit(self, bar, bar_idx, signal, countdown):
        """Devuelve (closed, pnl_pips, reason)."""
        if bar_idx - self.entry_bar >= countdown:
            return True, self._pnl(bar["c"]), "TIMEOUT"
        if (self.direction == "UP"   and signal == "DOWN") or \
           (self.direction == "DOWN" and signal == "UP"):
            return True, self._pnl(bar["c"]), "FLIP"
        if self.direction == "UP":
            if bar["l"] <= self.sl:
                return True, -abs(self.entry - self.sl) / self.pip_size - self.spread, "SL"
            if bar["h"] >= self.tp:
                return True,  abs(self.tp - self.entry) / self.pip_size - self.spread, "TP"
        else:
            if bar["h"] >= self.sl:
                return True, -abs(self.sl - self.entry) / self.pip_size - self.spread, "SL"
            if bar["l"] <= self.tp:
                return True,  abs(self.entry - self.tp) / self.pip_size - self.spread, "TP"
        return False, 0.0, ""

    def _pnl(self, price):
        pips = (price - self.entry) / self.pip_size
        if self.direction == "DOWN":
            pips = -pips
        return pips - self.spread


def simulate_symbol(symbol: str, candles: list[dict]) -> dict:
    pip    = _pip_size(symbol)
    spread = SPREAD_PIPS[symbol]
    trades = []
    current: Trade | None = None
    prev_signal = "NEUTRAL"

    for i in range(WARMUP_BARS, len(candles)):
        window = candles[max(0, i - 3500) : i]
        signal = compute_signal(window)
        bar = candles[i]

        if current:
            closed, pnl, reason = current.check_exit(bar, i, signal, COUNTDOWN_BARS)
            if closed:
                trades.append({"pnl": pnl, "reason": reason, "dir": current.direction})
                current = None

        if current is None and signal != "NEUTRAL" and (signal != prev_signal or prev_signal == "NEUTRAL"):
            atr_pips = _atr_14(candles[max(0, i - 20) : i + 1], symbol)
            if atr_pips > 0:
                atr_price = atr_pips * pip
                entry = bar["c"]
                if signal == "UP":
                    sl = entry - atr_price * ATR_SL_MULT
                    tp = entry + atr_price * ATR_TP_MULT
                else:
                    sl = entry + atr_price * ATR_SL_MULT
                    tp = entry - atr_price * ATR_TP_MULT
                current = Trade(signal, entry, sl, tp, i, pip, spread)

        prev_signal = signal

    if current:
        trades.append({"pnl": current._pnl(candles[-1]["c"]), "reason": "EOD", "dir": current.direction})

    return {"symbol": symbol, "trades": trades}


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def _metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    pnls   = [t["pnl"] for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    gp   = sum(wins)   if wins   else 0.0
    gl   = abs(sum(losses)) if losses else 1e-9
    mean = sum(pnls) / len(pnls)

    # Equity / drawdown
    equity = peak = max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Sharpe / Sortino (anualizados, asumiendo ~6 trades/día)
    std = math.sqrt(sum((p - mean) ** 2 for p in pnls) / len(pnls)) if len(pnls) > 1 else 0
    sharpe = (mean / std * math.sqrt(6 * 252)) if std > 0 else 0

    neg = [p for p in pnls if p < 0]
    down_std = math.sqrt(sum(p ** 2 for p in neg) / len(pnls)) if neg else 1e-9
    sortino = (mean / down_std * math.sqrt(6 * 252)) if down_std > 0 else 0

    # Racha de pérdidas
    max_streak = cur = 0
    for p in pnls:
        if p <= 0:
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0

    reasons = defaultdict(int)
    for t in trades:
        reasons[t.get("reason", "?")] += 1

    return {
        "trades":           len(pnls),
        "win_rate":         round(len(wins) / len(pnls) * 100, 1),
        "profit_factor":    round(gp / gl, 2),
        "avg_win":          round(sum(wins) / len(wins), 1) if wins else 0,
        "avg_loss":         round(abs(sum(losses) / len(losses)), 1) if losses else 0,
        "expectancy":       round(mean, 2),
        "total_pips":       round(sum(pnls), 1),
        "max_drawdown":     round(max_dd, 1),
        "sharpe":           round(sharpe, 2),
        "sortino":          round(sortino, 2),
        "max_loss_streak":  max_streak,
        "exits":            dict(reasons),
    }


def compute_metrics(results: list[dict]) -> dict:
    all_trades = []
    per_pair = {}
    for r in results:
        per_pair[r["symbol"]] = _metrics(r["trades"])
        all_trades.extend(r["trades"])
    return {"overall": _metrics(all_trades), "per_pair": per_pair}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
SEP = "=" * 62

def _print_block(m: dict, indent: str = "  "):
    if not m.get("trades"):
        print(f"{indent}Sin operaciones.")
        return
    i = indent
    print(f"{i}Operaciones:         {m['trades']}")
    print(f"{i}Win rate:            {m['win_rate']}%")
    print(f"{i}Profit factor:       {m['profit_factor']}")
    print(f"{i}Ganancia promedio:   {m['avg_win']} pips")
    print(f"{i}Perdida promedio:    {m['avg_loss']} pips")
    print(f"{i}Expectancy:          {m['expectancy']} pips/op")
    print(f"{i}Total pips:          {m['total_pips']}")
    print(f"{i}Max drawdown:        {m['max_drawdown']} pips")
    print(f"{i}Sharpe ratio:        {m['sharpe']}")
    print(f"{i}Sortino ratio:       {m['sortino']}")
    print(f"{i}Racha pérd. máx:     {m['max_loss_streak']}")
    exits = m.get("exits", {})
    print(f"{i}Salidas:             TP={exits.get('TP',0)}  SL={exits.get('SL',0)}  "
          f"TIMEOUT={exits.get('TIMEOUT',0)}  FLIP={exits.get('FLIP',0)}  EOD={exits.get('EOD',0)}")


def main():
    print(SEP)
    print("  ATLAS Backtest Simulator - 60 dias M5 - 6 Timeframes")
    rr = round(ATR_TP_MULT / ATR_SL_MULT, 1)
    print(f"  Config: SL={ATR_SL_MULT}xATR  TP={ATR_TP_MULT}xATR  "
          f"RR={rr}  MinAlineados={MIN_ALIGNED}/6")
    print(SEP)

    results = []
    for idx, sym in enumerate(SYMBOLS):
        if idx > 0:
            time.sleep(4)
        print(f"  [{sym}] descargando...", end=" ", flush=True)
        try:
            candles = fetch_candles(sym)
            print(f"{len(candles)} velas -> simulando...", end=" ", flush=True)
            if len(candles) < WARMUP_BARS + 100:
                print("SKIP (insuficiente)")
                continue
            r = simulate_symbol(sym, candles)
            results.append(r)
            t = r["trades"]
            wr = round(sum(1 for x in t if x["pnl"] > 0) / len(t) * 100, 1) if t else 0
            print(f"{len(t)} ops  WR={wr}%")
        except Exception as e:
            print(f"ERROR: {e}")

    if not results:
        print("\nSin datos suficientes para simular.")
        return

    metrics = compute_metrics(results)

    print()
    print(SEP)
    print("  MÉTRICAS GLOBALES (todos los pares)")
    print(SEP)
    _print_block(metrics["overall"])

    print()
    print(SEP)
    print("  MÉTRICAS POR PAR")
    print(SEP)
    for sym, m in metrics["per_pair"].items():
        star = "★" if m.get("profit_factor", 0) >= 1.5 else " "
        print(f"\n{star} {sym}  ({m.get('trades', 0)} ops)")
        _print_block(m, "    ")

    print()
    print(SEP)
    overall = metrics["overall"]
    pf = overall.get("profit_factor", 0)
    wr = overall.get("win_rate", 0)
    verdict = "POSITIVO" if pf >= 1.2 and wr >= 45 else "MARGINAL" if pf >= 1.0 else "NEGATIVO"
    print(f"  VEREDICTO: {verdict}  |  PF={pf}  WR={wr}%  Pips={overall.get('total_pips', 0)}")
    print(SEP)


if __name__ == "__main__":
    main()
