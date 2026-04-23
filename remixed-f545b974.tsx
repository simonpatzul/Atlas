import { useEffect, useMemo, useRef, useState } from "react";

const PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "AUD/USD", "USD/CAD", "USD/CHF"];
const PREDICTION_HORIZONS = {
  "5m": { label: "5M", chartLabel: "5M", countdownSec: 300, steps: 1, dt: 1 / 288, rangeMultiplier: 0.2 },
  "1h": { label: "1H", chartLabel: "1H", countdownSec: 3600, steps: 12, dt: 1 / 24, rangeMultiplier: 1 },
  "1d": { label: "1D", chartLabel: "1D", countdownSec: 86400, steps: 24, dt: 1 / 24, rangeMultiplier: 6 },
};

const getDec = (pair) => (pair === "USD/JPY" ? 2 : pair === "XAU/USD" ? 1 : 4);
const getPipSize = (pair) => (pair === "USD/JPY" ? 0.01 : pair === "XAU/USD" ? 0.1 : 0.0001);
const fmt = (pair, value) => (value != null ? Number(value).toFixed(getDec(pair)) : "-");
const fmtT = (date) => date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const scoreCol = (score) => (score >= 65 ? "#00e87a" : score <= 35 ? "#ff4060" : "#ffaa00");
const biasCol = (bias) =>
  bias === "ALCISTA" ? "#00e87a" : bias === "BAJISTA" ? "#ff4060" : "#ffaa00";
const rsiCol = (value) =>
  value >= 70 ? "#ff4060" : value >= 55 ? "#00e87a" : value <= 30 ? "#00d4ff" : value <= 45 ? "#ff4060" : "#8899aa";

const biasLabel = (bias) =>
  bias === "UP" ? "ALCISTA" : bias === "DOWN" ? "BAJISTA" : "NEUTRO";

const API_BASE = (import.meta.env.VITE_ATLAS_API_BASE || "").replace(/\/$/, "");

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${path}`);
  }
  return response.json();
}

function calcEMA(closes, period) {
  if (!closes.length) return [];
  const k = 2 / (period + 1);
  let ema = closes[0];
  return closes.map((close) => {
    ema = close * k + ema * (1 - k);
    return ema;
  });
}

function calcBollinger(closes, period = 20, mult = 2) {
  return closes.map((_, index) => {
    if (index < period - 1) return null;
    const slice = closes.slice(index - period + 1, index + 1);
    const mean = slice.reduce((sum, value) => sum + value, 0) / period;
    const std = Math.sqrt(slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / period);
    return { mid: mean, upper: mean + mult * std, lower: mean - mult * std, std };
  });
}

function calcRSI(closes, period = 14) {
  if (closes.length < period + 1) return closes.map(() => null);
  const gains = [];
  const losses = [];
  for (let i = 1; i < closes.length; i += 1) {
    const delta = closes[i] - closes[i - 1];
    gains.push(delta > 0 ? delta : 0);
    losses.push(delta < 0 ? -delta : 0);
  }

  const rsi = [null];
  let avgG = gains.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  let avgL = losses.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  rsi.push(100 - 100 / (1 + avgG / Math.max(avgL, 1e-10)));

  for (let i = period; i < gains.length; i += 1) {
    avgG = (avgG * (period - 1) + gains[i]) / period;
    avgL = (avgL * (period - 1) + losses[i]) / period;
    rsi.push(100 - 100 / (1 + avgG / Math.max(avgL, 1e-10)));
  }

  while (rsi.length < closes.length) rsi.unshift(null);
  return rsi;
}

function calcMACD(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const macd = emaFast.map((value, index) => value - emaSlow[index]);
  const signalLine = calcEMA(macd, signal);
  const hist = macd.map((value, index) => value - signalLine[index]);
  return { macd, signal: signalLine, hist };
}

function calcFibonacci(candles) {
  if (!candles.length) return null;
  const highs = candles.map((candle) => candle.h);
  const lows = candles.map((candle) => candle.l);
  const swingHigh = Math.max(...highs);
  const swingLow = Math.min(...lows);
  const range = swingHigh - swingLow;
  return {
    h: swingHigh,
    l: swingLow,
    r236: swingHigh - range * 0.236,
    r382: swingHigh - range * 0.382,
    r500: swingHigh - range * 0.5,
    r618: swingHigh - range * 0.618,
    r786: swingHigh - range * 0.786,
  };
}

function detectSR(candles, zones = 4) {
  if (!candles.length) return [];
  const prices = candles.flatMap((candle) => [candle.h, candle.l]).sort((a, b) => a - b);
  const tolerance = (Math.max(...prices) - Math.min(...prices)) * 0.008;
  const clusters = [];

  prices.forEach((price) => {
    const existing = clusters.find((cluster) => Math.abs(cluster.price - price) < tolerance);
    if (existing) {
      existing.count += 1;
      existing.price = (existing.price * (existing.count - 1) + price) / existing.count;
    } else {
      clusters.push({ price, count: 1 });
    }
  });

  return clusters.sort((a, b) => b.count - a.count).slice(0, zones * 2);
}

function calcTechScore(pair, closes, rsiVals, bb, macdData, ema9, ema21, ema50) {
  if (closes.length < 30) return { score: 50, signals: [{ l: "Sin suficientes velas reales", pts: 0, c: "#8899aa" }] };

  const last = closes.length - 1;
  const price = closes[last];
  const e9 = ema9[last];
  const e21 = ema21[last];
  const e50 = ema50[last];
  const rsi = rsiVals[last] ?? 50;
  const bbLast = bb[last];
  const macdHist = macdData.hist[last] ?? 0;
  const macdPrev = macdData.hist[last - 1] ?? 0;
  const roc5 = last >= 5 ? ((closes[last] - closes[last - 5]) / closes[last - 5]) * 100 : 0;

  let score = 50;
  const signals = [];

  if (e9 > e21 && e21 > e50) {
    score += 12;
    signals.push({ l: "EMA 9>21>50: tendencia alcista", pts: +12, c: "#00e87a" });
  } else if (e9 < e21 && e21 < e50) {
    score -= 12;
    signals.push({ l: "EMA 9<21<50: tendencia bajista", pts: -12, c: "#ff4060" });
  } else {
    signals.push({ l: "EMAs cruzadas: rango o transición", pts: 0, c: "#8899aa" });
  }

  if (price > e50) {
    score += 6;
    signals.push({ l: `Precio sobre EMA50 (${fmt(pair, e50)})`, pts: +6, c: "#00e87a" });
  } else {
    score -= 6;
    signals.push({ l: `Precio bajo EMA50 (${fmt(pair, e50)})`, pts: -6, c: "#ff4060" });
  }

  if (rsi > 70) {
    score -= 8;
    signals.push({ l: `RSI sobrecomprado (${rsi.toFixed(1)})`, pts: -8, c: "#ff4060" });
  } else if (rsi < 30) {
    score += 8;
    signals.push({ l: `RSI sobrevendido (${rsi.toFixed(1)})`, pts: +8, c: "#00d4ff" });
  } else if (rsi > 55) {
    score += 5;
    signals.push({ l: `RSI alcista (${rsi.toFixed(1)})`, pts: +5, c: "#00e87a" });
  } else if (rsi < 45) {
    score -= 5;
    signals.push({ l: `RSI bajista (${rsi.toFixed(1)})`, pts: -5, c: "#ff4060" });
  } else {
    signals.push({ l: `RSI neutro (${rsi.toFixed(1)})`, pts: 0, c: "#8899aa" });
  }

  if (bbLast) {
    if (price > bbLast.upper) {
      score -= 7;
      signals.push({ l: "Precio sobre BB superior", pts: -7, c: "#ff4060" });
    } else if (price < bbLast.lower) {
      score += 7;
      signals.push({ l: "Precio bajo BB inferior", pts: +7, c: "#00e87a" });
    } else if (price > bbLast.mid) {
      score += 3;
      signals.push({ l: "Precio en mitad alta de Bollinger", pts: +3, c: "#00e87a" });
    } else {
      score -= 3;
      signals.push({ l: "Precio en mitad baja de Bollinger", pts: -3, c: "#ff4060" });
    }
  }

  if (macdHist > 0 && macdHist > macdPrev) {
    score += 6;
    signals.push({ l: "MACD histograma creciendo", pts: +6, c: "#00e87a" });
  } else if (macdHist < 0 && macdHist < macdPrev) {
    score -= 6;
    signals.push({ l: "MACD histograma decreciendo", pts: -6, c: "#ff4060" });
  } else if (macdHist > 0) {
    score += 2;
    signals.push({ l: "MACD positivo pero desacelerando", pts: +2, c: "#ffaa00" });
  } else {
    score -= 2;
    signals.push({ l: "MACD negativo pero recuperando", pts: -2, c: "#ffaa00" });
  }

  if (Math.abs(roc5) > 0.15) {
    const pts = roc5 > 0 ? 4 : -4;
    score += pts;
    signals.push({
      l: `Momentum ROC(5): ${roc5 > 0 ? "+" : ""}${roc5.toFixed(3)}%`,
      pts,
      c: roc5 > 0 ? "#00e87a" : "#ff4060",
    });
  }

  return { score: clamp(Math.round(score), 0, 100), signals };
}

function randn() {
  const u = Math.max(Math.random(), 1e-12);
  const v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function estimateStepVol(closes) {
  if (closes.length < 20) return 0.0001;
  const returns = [];
  for (let i = 1; i < closes.length; i += 1) {
    returns.push(Math.log(closes[i] / closes[i - 1]));
  }
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / returns.length;
  return Math.max(Math.sqrt(variance), 0.00005);
}

function monteCarlo(pair, candles, context, combinedScore, horizonKey) {
  const closes = candles.map((candle) => candle.c);
  const price = closes.at(-1);
  if (!price || closes.length < 20) return null;

  const horizon = PREDICTION_HORIZONS[horizonKey] ?? PREDICTION_HORIZONS["1h"];
  const tfContext =
    horizonKey === "5m" ? context.timeframe_5m :
    horizonKey === "1d" ? context.timeframe_1d :
    context.timeframe_1h;
  const directionBias = tfContext?.bias ?? context.bias;
  const dir = directionBias === "UP" ? 1 : directionBias === "DOWN" ? -1 : 0;
  const confidence = tfContext?.confidence ?? context.confidence ?? 50;
  const stepVol = estimateStepVol(closes);
  const expectedRangePips = (context.expected_range_1h_pips ?? 10) * horizon.rangeMultiplier;
  const atrVol = (expectedRangePips * getPipSize(pair)) / Math.max(price, 1e-8) / Math.max(horizon.steps / 2, 1);
  const sigma = Math.max(stepVol, atrVol);
  const mu = dir * sigma * ((confidence - 50) / 50) * 0.45;
  const n = 400;
  const steps = horizon.steps;
  const dt = horizon.dt;

  const paths = Array.from({ length: n }, () => {
    let p = price;
    const path = [p];
    for (let t = 0; t < steps; t += 1) {
      p = p * Math.exp((mu - 0.5 * sigma * sigma) * dt + sigma * Math.sqrt(dt) * randn());
      path.push(p);
    }
    return path;
  });

  const stats = Array.from({ length: steps + 1 }, (_, t) => {
    const values = [...paths.map((path) => path[t])].sort((a, b) => a - b);
    const mean = values.reduce((sum, value) => sum + value, 0) / n;
    const std = Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / n);
    return {
      mean,
      std,
      p5: values[Math.floor(n * 0.05)],
      p10: values[Math.floor(n * 0.1)],
      p25: values[Math.floor(n * 0.25)],
      p50: values[Math.floor(n * 0.5)],
      p75: values[Math.floor(n * 0.75)],
      p90: values[Math.floor(n * 0.9)],
      p95: values[Math.floor(n * 0.95)],
    };
  });

  const last = stats[steps];
  const pipSize = getPipSize(pair);
  const target = last.p50;
  const tp = dir >= 0 ? last.p75 : last.p25;
  const tp2 = dir >= 0 ? last.p90 : last.p10;
  const sl = dir >= 0 ? last.p5 : last.p95;
  const pips = Math.round((target - price) / pipSize);
  const bullishPaths = paths.filter((path) => path[steps] > price).length;
  const conf = dir >= 0 ? (bullishPaths / n) * 100 : (1 - bullishPaths / n) * 100;
  const rr = Math.abs(tp - price) / Math.max(Math.abs(sl - price), 1e-10);

  const finalPrices = paths.map((path) => path[steps]).sort((a, b) => a - b);
  const binCount = 20;
  const binMin = finalPrices[0];
  const binMax = finalPrices[n - 1];
  const binSize = Math.max((binMax - binMin) / binCount, 1e-10);
  const bins = Array.from({ length: binCount }, (_, index) => ({
    lo: binMin + index * binSize,
    hi: binMin + (index + 1) * binSize,
    count: 0,
  }));

  finalPrices.forEach((value) => {
    const idx = Math.min(Math.floor((value - binMin) / binSize), binCount - 1);
    bins[idx].count += 1;
  });

  return {
    horizonKey,
    horizonLabel: horizon.label,
    chartLabel: horizon.chartLabel,
    countdownSec: horizon.countdownSec,
    steps,
    stats,
    target,
    tp,
    tp2,
    sl,
    pips,
    conf,
    rr,
    dir,
    bins,
    finalPrices,
    n,
    combinedScore,
    variance: last.std ** 2,
    skewness: (() => {
      const mean = last.mean;
      const std = last.std || 1e-10;
      return finalPrices.reduce((sum, value) => sum + (value - mean) ** 3, 0) / (n * std ** 3);
    })(),
    kurtosis: (() => {
      const mean = last.mean;
      const std = last.std || 1e-10;
      return finalPrices.reduce((sum, value) => sum + (value - mean) ** 4, 0) / (n * std ** 4) - 3;
    })(),
  };
}

function EmptyState({ text }) {
  return (
    <div
      style={{
        background: "#040d18",
        border: "1px solid #0c1e32",
        borderRadius: "6px",
        padding: "24px",
        textAlign: "center",
        color: "#5f7a92",
        fontSize: "12px",
      }}
    >
      {text}
    </div>
  );
}

function Chart({ pair, candles, mc, ema9, ema21, ema50, bb, srZones, fibs, showEMA, showBB, showFib, showSR }) {
  if (!candles.length) return <EmptyState text="Cargando velas reales..." />;

  const width = 820;
  const height = 400;
  const pad = { top: 28, right: 80, bottom: 28, left: 72 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const predSteps = mc?.steps ?? 0;
  const totalBars = candles.length + predSteps + 1;
  const barWidth = chartW / totalBars;
  const histEnd = candles.length;

  const allValues = [
    ...candles.flatMap((candle) => [candle.h, candle.l]),
    ...bb.filter(Boolean).flatMap((band) => [band.upper, band.lower]),
    ...(mc ? mc.stats.flatMap((stat) => [stat.p5, stat.p95]) : []),
  ];
  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const padding = (rawMax - rawMin) * 0.08 || 1;
  const minV = rawMin - padding;
  const maxV = rawMax + padding;
  const range = maxV - minV;
  const toX = (index) => pad.left + index * barWidth + barWidth / 2;
  const toY = (value) => pad.top + chartH - ((value - minV) / range) * chartH;
  const currentPrice = candles.at(-1)?.c ?? 0;
  const d = getDec(pair);
  const yTicks = Array.from({ length: 7 }, (_, index) => minV + (range / 6) * index);
  const separatorX = toX(histEnd);

  const bbUpper = bb.map((band, index) => (band ? `${toX(index)},${toY(band.upper)}` : "")).filter(Boolean);
  const bbLower = bb.map((band, index) => (band ? `${toX(index)},${toY(band.lower)}` : "")).filter(Boolean);
  const bbMid = bb.map((band, index) => (band ? `${toX(index)},${toY(band.mid)}` : "")).filter(Boolean);
  const bbPolygon = bbUpper.length ? [...bbUpper, ...[...bbLower].reverse()].join(" ") : null;
  const medLine = mc ? mc.stats.map((stat, index) => `${toX(histEnd + index)},${toY(stat.p50)}`).join(" ") : null;
  const band90 = mc
    ? [
        ...mc.stats.map((stat, index) => `${toX(histEnd + index)},${toY(stat.p95)}`),
        ...[...mc.stats].reverse().map((stat, index) => `${toX(histEnd + mc.stats.length - 1 - index)},${toY(stat.p5)}`),
      ].join(" ")
    : null;
  const band50 = mc
    ? [
        ...mc.stats.map((stat, index) => `${toX(histEnd + index)},${toY(stat.p75)}`),
        ...[...mc.stats].reverse().map((stat, index) => `${toX(histEnd + mc.stats.length - 1 - index)},${toY(stat.p25)}`),
      ].join(" ")
    : null;

  const emaPath = (series, color, dash = "") => {
    const path = series
      .map((value, index) => (value ? `${index === 0 || !series[index - 1] ? "M" : "L"}${toX(index)},${toY(value)}` : ""))
      .filter(Boolean)
      .join(" ");
    return path ? <path key={color} d={path} fill="none" stroke={color} strokeWidth="1.2" strokeDasharray={dash} opacity="0.85" /> : null;
  };

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block", background: "#040d18", borderRadius: "6px", border: "1px solid #0c1e32" }}>
      {yTicks.map((value, index) => (
        <g key={index}>
          <line x1={pad.left} y1={toY(value)} x2={pad.left + chartW} y2={toY(value)} stroke="#080f1e" strokeWidth="1" />
          <text x={pad.left - 5} y={toY(value) + 4} textAnchor="end" fill="#1a3a54" fontSize="8.5" fontFamily="monospace">
            {Number(value.toFixed(d + 1))}
          </text>
        </g>
      ))}

      {showFib &&
        fibs &&
        [
          { v: fibs.r236, l: "23.6%", c: "#9966ff" },
          { v: fibs.r382, l: "38.2%", c: "#6644ff" },
          { v: fibs.r500, l: "50.0%", c: "#4466ff" },
          { v: fibs.r618, l: "61.8%", c: "#2288ff" },
          { v: fibs.r786, l: "78.6%", c: "#00aaff" },
        ].map((fib) => (
          <g key={fib.l}>
            <line x1={pad.left} y1={toY(fib.v)} x2={pad.left + chartW} y2={toY(fib.v)} stroke={fib.c} strokeWidth="0.7" strokeDasharray="6,4" opacity="0.5" />
            <text x={pad.left + 2} y={toY(fib.v) - 3} fill={fib.c} fontSize="7.5" fontFamily="monospace" opacity="0.8">
              Fib {fib.l}
            </text>
          </g>
        ))}

      {showSR &&
        srZones.map((zone, index) => {
          const isResistance = zone.price > currentPrice;
          return (
            <line
              key={index}
              x1={pad.left}
              y1={toY(zone.price)}
              x2={pad.left + chartW}
              y2={toY(zone.price)}
              stroke={isResistance ? "#ff4060" : "#00e87a"}
              strokeWidth="0.8"
              strokeDasharray="3,4"
              opacity="0.45"
            />
          );
        })}

      {showBB && bbPolygon && (
        <>
          <polygon points={bbPolygon} fill="rgba(0,180,255,0.04)" stroke="none" />
          <polyline points={bbUpper.join(" ")} fill="none" stroke="#0088cc" strokeWidth="0.9" opacity="0.6" strokeDasharray="4,3" />
          <polyline points={bbLower.join(" ")} fill="none" stroke="#0088cc" strokeWidth="0.9" opacity="0.6" strokeDasharray="4,3" />
          <polyline points={bbMid.join(" ")} fill="none" stroke="#0066aa" strokeWidth="0.7" opacity="0.4" strokeDasharray="2,3" />
        </>
      )}

      {showEMA && (
        <>
          {emaPath(ema9, "#ff9900")}
          {emaPath(ema21, "#00ccff")}
          {emaPath(ema50, "#cc44ff")}
        </>
      )}

      {mc && (
        <>
          <line x1={separatorX} y1={pad.top} x2={separatorX} y2={pad.top + chartH} stroke="#1a3a54" strokeWidth="1" strokeDasharray="5,3" />
          <text x={separatorX - 2} y={pad.top - 8} textAnchor="end" fill="#1a3a54" fontSize="8" fontFamily="monospace">
            HIST
          </text>
          <text x={separatorX + 2} y={pad.top - 8} fill="#2a5a7a" fontSize="8" fontFamily="monospace">
            PREDICCIÓN {mc.chartLabel} →
          </text>
          <polygon points={band90} fill="rgba(0,212,255,0.06)" stroke="none" />
          <polygon points={band50} fill="rgba(0,212,255,0.13)" stroke="none" />
        </>
      )}

      {candles.map((candle, index) => {
        const x = toX(index);
        const up = candle.c >= candle.o;
        const color = up ? "#00e87a" : "#ff4060";
        const boxY = toY(Math.max(candle.o, candle.c));
        const boxH = Math.max(1.5, Math.abs(toY(candle.o) - toY(candle.c)));
        return (
          <g key={candle.ts_utc}>
            <line x1={x} y1={toY(candle.h)} x2={x} y2={toY(candle.l)} stroke={color} strokeWidth="0.9" opacity="0.8" />
            <rect x={x - barWidth * 0.38} y={boxY} width={barWidth * 0.76} height={boxH} fill={up ? color : "none"} stroke={color} strokeWidth="0.8" opacity="0.9" />
          </g>
        );
      })}

      {mc && medLine && (
        <>
          <polyline points={medLine} fill="none" stroke="#00d4ff" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
          <line x1={separatorX} y1={toY(mc.tp2)} x2={pad.left + chartW} y2={toY(mc.tp2)} stroke="#00ff88" strokeWidth="0.8" strokeDasharray="3,3" opacity="0.6" />
          <line x1={separatorX} y1={toY(mc.tp)} x2={pad.left + chartW} y2={toY(mc.tp)} stroke="#00e87a" strokeWidth="1.2" strokeDasharray="5,3" opacity="0.8" />
          <line x1={separatorX} y1={toY(mc.target)} x2={pad.left + chartW} y2={toY(mc.target)} stroke="#00d4ff" strokeWidth="1" strokeDasharray="2,2" opacity="0.5" />
          <line x1={separatorX} y1={toY(mc.sl)} x2={pad.left + chartW} y2={toY(mc.sl)} stroke="#ff4060" strokeWidth="1.2" strokeDasharray="5,3" opacity="0.8" />
        </>
      )}

      {[0, 10, 20, 30, 40, candles.length - 1].map((index, i) => {
        const candle = candles[index];
        if (!candle) return null;
        return (
          <text key={i} x={toX(index)} y={pad.top + chartH + 14} textAnchor="middle" fill="#1a3a54" fontSize="8" fontFamily="monospace">
            {fmtT(candle.t)}
          </text>
        );
      })}
    </svg>
  );
}

function RSIChart({ rsiVals }) {
  if (!rsiVals.length) return null;
  const width = 820;
  const height = 80;
  const pad = { top: 8, right: 80, bottom: 14, left: 72 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const n = rsiVals.length;
  const barWidth = chartW / n;
  const toX = (index) => pad.left + index * barWidth + barWidth / 2;
  const toY = (value) => pad.top + chartH - (value / 100) * chartH;
  const points = rsiVals.map((value, index) => (value != null ? `${toX(index)},${toY(value)}` : "")).filter(Boolean).join(" ");
  const last = rsiVals.filter(Boolean).pop() ?? 50;

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block", background: "#040d18", borderTop: "1px solid #0a1828" }}>
      {[30, 50, 70].map((value) => (
        <g key={value}>
          <line x1={pad.left} y1={toY(value)} x2={pad.left + chartW} y2={toY(value)} stroke={value === 50 ? "#0c1e30" : "#0a1828"} strokeWidth="1" strokeDasharray={value !== 50 ? "3,3" : ""} />
          <text x={pad.left - 5} y={toY(value) + 4} textAnchor="end" fill="#1a3a54" fontSize="8" fontFamily="monospace">
            {value}
          </text>
        </g>
      ))}
      <rect x={pad.left} y={toY(100)} width={chartW} height={toY(70) - toY(100)} fill="rgba(255,64,96,.06)" />
      <rect x={pad.left} y={toY(30)} width={chartW} height={toY(0) - toY(30)} fill="rgba(0,232,122,.06)" />
      <polyline points={points} fill="none" stroke={rsiCol(last)} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

function MACDChart({ macdData }) {
  if (!macdData.macd.length) return null;
  const width = 820;
  const height = 80;
  const pad = { top: 8, right: 80, bottom: 14, left: 72 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const n = macdData.macd.length;
  const barWidth = chartW / n;
  const toX = (index) => pad.left + index * barWidth + barWidth / 2;

  const values = [...macdData.macd, ...macdData.signal, ...macdData.hist].filter((value) => value != null);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = Math.max(Math.abs(minV), Math.abs(maxV)) * 2.2 || 1;
  const toY = (value) => pad.top + chartH / 2 - (value / range) * chartH;

  const macdPoints = macdData.macd.map((value, index) => (value != null ? `${toX(index)},${toY(value)}` : "")).filter(Boolean).join(" ");
  const signalPoints = macdData.signal.map((value, index) => (value != null ? `${toX(index)},${toY(value)}` : "")).filter(Boolean).join(" ");

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block", background: "#040d18", borderTop: "1px solid #0a1828" }}>
      <line x1={pad.left} y1={toY(0)} x2={pad.left + chartW} y2={toY(0)} stroke="#0c1e30" strokeWidth="1" />
      {macdData.hist.map((value, index) => {
        if (value == null) return null;
        const x = toX(index);
        const y0 = toY(0);
        const yv = toY(value);
        return (
          <rect
            key={index}
            x={x - barWidth * 0.38}
            y={Math.min(y0, yv)}
            width={barWidth * 0.76}
            height={Math.max(1, Math.abs(y0 - yv))}
            fill={value >= 0 ? "rgba(0,232,122,.7)" : "rgba(255,64,96,.7)"}
          />
        );
      })}
      <polyline points={macdPoints} fill="none" stroke="#00ccff" strokeWidth="1.5" strokeLinejoin="round" />
      <polyline points={signalPoints} fill="none" stroke="#ff9900" strokeWidth="1.2" strokeDasharray="4,2" />
    </svg>
  );
}

function VolumeChart({ candles }) {
  if (!candles.length) return null;
  const width = 820;
  const height = 55;
  const pad = { top: 5, right: 80, bottom: 12, left: 72 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const n = candles.length;
  const barWidth = chartW / (n + 13);
  const toX = (index) => pad.left + index * barWidth + barWidth / 2;
  const maxV = Math.max(...candles.map((candle) => candle.v || 1), 1);
  const toH = (value) => (value / maxV) * chartH;

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block", background: "#040d18", borderTop: "1px solid #0a1828" }}>
      {candles.map((candle, index) => {
        const x = toX(index);
        const h = toH(candle.v || 0);
        const up = candle.c >= candle.o;
        return (
          <rect
            key={candle.ts_utc}
            x={x - barWidth * 0.38}
            y={pad.top + chartH - h}
            width={barWidth * 0.76}
            height={Math.max(1, h)}
            fill={up ? "rgba(0,232,122,.5)" : "rgba(255,64,96,.5)"}
          />
        );
      })}
    </svg>
  );
}

function DistChart({ mc, pair }) {
  if (!mc) return null;
  const width = 260;
  const height = 120;
  const pad = { top: 18, right: 12, bottom: 20, left: 12 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const maxCount = Math.max(...mc.bins.map((bin) => bin.count), 1);
  const barWidth = chartW / mc.bins.length;
  const current = mc.stats[0].p50;

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block", background: "#040d18", borderRadius: "4px", border: "1px solid #0c1e32" }}>
      <text x={width / 2} y={13} textAnchor="middle" fill="#1a4060" fontSize="9" fontFamily="monospace" letterSpacing="1">
        DISTRIBUCIÓN FINAL ({mc.chartLabel})
      </text>
      {mc.bins.map((bin, index) => {
        const h = (bin.count / maxCount) * chartH;
        const x = pad.left + index * barWidth;
        const isBull = bin.lo > current;
        const isBear = bin.hi < current;
        return (
          <rect
            key={index}
            x={x}
            y={pad.top + chartH - h}
            width={Math.max(1, barWidth - 0.5)}
            height={h}
            fill={isBull ? "rgba(0,232,122,.7)" : isBear ? "rgba(255,64,96,.7)" : "rgba(0,212,255,.5)"}
          />
        );
      })}
      <text x={width / 2} y={height - 4} textAnchor="middle" fill="#1a4060" fontSize="8" fontFamily="monospace">
        μ={fmt(pair, mc.stats.at(-1)?.mean)} σ={fmt(pair, mc.stats.at(-1)?.std)}
      </text>
    </svg>
  );
}

function LayerToggles({ toggles }) {
  return (
    <div style={{ display: "flex", gap: "5px", alignItems: "center" }}>
      <span style={{ fontSize: "8px", color: "#1a4060", marginRight: "2px", letterSpacing: "1px" }}>CAPAS:</span>
      {toggles.map((toggle) => (
        <button key={toggle.lbl} className={`tog${toggle.val ? " on" : ""}`} onClick={() => toggle.set(!toggle.val)}>
          {toggle.lbl}
        </button>
      ))}
    </div>
  );
}

function TechnicalSignalsPanel({ techScore, mc, pair }) {
  return (
    <div style={{ marginTop: "8px", display: "flex", gap: "8px", alignItems: "flex-start" }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "5px" }}>
          SEÑALES TÉCNICAS REALES — SCORE {techScore.score}/100
        </div>
        <div style={{ maxHeight: "96px", overflowY: "auto" }}>
          {techScore.signals.map((signal, index) => (
            <div key={index} className="sig-row">
              <span style={{ fontSize: "10px", color: "#7a9abb", flex: 1 }}>{signal.l}</span>
              <span style={{ fontSize: "11px", fontWeight: 800, color: signal.c, fontFamily: "'Orbitron',monospace", marginLeft: "8px" }}>
                {signal.pts > 0 ? "+" : ""}
                {signal.pts}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ width: "260px" }}>
        <DistChart mc={mc} pair={pair} />
      </div>
    </div>
  );
}

function MetricsCard({ rows }) {
  return (
    <div className="card">
      {rows.map((row) => (
        <div key={row.l} className="sr">
          <span style={{ color: "#1a4060" }}>{row.l}</span>
          <span style={{ color: row.c, fontWeight: 600, fontSize: "10px" }}>{row.v}</span>
        </div>
      ))}
    </div>
  );
}

function PredictionPanel({ mc, pair, combinedBias, running, context, candles, onPredict, predictionHorizon }) {
  return (
    <>
      <button className="pred-btn" style={{ width: "100%", marginBottom: "8px" }} onClick={onPredict} disabled={running || !context || !candles.length}>
        {running ? "⟳ CALCULANDO..." : `⚡ PREDECIR ${PREDICTION_HORIZONS[predictionHorizon].label}`}
      </button>

      {mc && (
        <>
          <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "5px" }}>PREDICCIÓN SOBRE DATOS REALES</div>
          <div style={{ display: "flex", gap: "5px", marginBottom: "6px" }}>
            {[
              { v: `${mc.pips >= 0 ? "+" : ""}${mc.pips}`, l: "PIPS", c: mc.pips >= 0 ? "#00e87a" : "#ff4060" },
              { v: `${mc.conf.toFixed(0)}%`, l: "CONF", c: mc.conf >= 60 ? "#00e87a" : "#ffaa00" },
              { v: `${mc.rr.toFixed(1)}:1`, l: "R/R", c: mc.rr >= 1.5 ? "#00e87a" : "#ffaa00" },
            ].map((metric) => (
              <div key={metric.l} className="metric">
                <div className="mval" style={{ color: metric.c, fontSize: "14px" }}>{metric.v}</div>
                <div className="mlbl">{metric.l}</div>
              </div>
            ))}
          </div>
          <MetricsCard
            rows={[
              { l: `Objetivo ${mc.horizonLabel}`, v: fmt(pair, mc.target), c: biasCol(combinedBias) },
              { l: "TP1", v: fmt(pair, mc.tp), c: "#00e87a" },
              { l: "TP2", v: fmt(pair, mc.tp2), c: "#00ff88" },
              { l: "Stop Loss", v: fmt(pair, mc.sl), c: "#ff4060" },
            ]}
          />
        </>
      )}
    </>
  );
}

function SidebarPanel(props) {
  const {
    combinedBias,
    combinedScore,
    predict,
    running,
    context,
    candles,
    mc,
    pair,
    livePrice,
    previousClose,
    market,
    lastRSI,
    lastE9,
    lastE21,
    lastE50,
    lastBB,
    lastMACD,
    techScore,
    providers,
    predTime,
    predictionHorizon,
    onChangePredictionHorizon,
  } = props;
  const tf5m = context?.timeframe_5m;
  const tf1h = context?.timeframe_1h;
  const tf1d = context?.timeframe_1d;
  const session = context?.session;
  const eventBlock = context?.event_block;

  return (
    <div style={{ width: "250px", minWidth: "250px", background: "#060e1a", borderLeft: "1px solid #0a1828", overflowY: "auto", padding: "10px" }}>
      <div style={{ background: combinedBias === "ALCISTA" ? "rgba(0,232,122,.07)" : combinedBias === "BAJISTA" ? "rgba(255,64,96,.07)" : "rgba(255,170,0,.05)", border: `1px solid ${biasCol(combinedBias)}33`, borderRadius: "4px", padding: "12px", marginBottom: "8px", textAlign: "center" }}>
        <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "4px" }}>SCORE COMBINADO REAL</div>
        <div style={{ fontFamily: "'Orbitron',monospace", fontSize: "36px", fontWeight: 900, color: scoreCol(combinedScore), lineHeight: 1 }}>{combinedScore}</div>
        <div style={{ fontSize: "11px", fontWeight: 700, color: biasCol(combinedBias), marginTop: "4px" }}>
          {combinedBias === "ALCISTA" ? "▲ ALCISTA" : combinedBias === "BAJISTA" ? "▼ BAJISTA" : "◆ NEUTRO"}
        </div>
        <div style={{ fontSize: "8px", color: "#1a4060", marginTop: "3px" }}>Técnico real + contexto real API</div>
      </div>

      <PredictionPanel mc={mc} pair={pair} combinedBias={combinedBias} running={running} context={context} candles={candles} onPredict={predict} predictionHorizon={predictionHorizon} />
      <div style={{ display: "flex", gap: "5px", marginBottom: "8px" }}>
        {Object.entries(PREDICTION_HORIZONS).map(([key, horizon]) => (
          <button
            key={key}
            className={`tog${predictionHorizon === key ? " on" : ""}`}
            style={{ flex: 1 }}
            onClick={() => onChangePredictionHorizon(key)}
          >
            {horizon.label}
          </button>
        ))}
      </div>

      <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "5px", marginTop: "6px" }}>MERCADO REAL</div>
      <MetricsCard
        rows={[
          { l: "Último", v: fmt(pair, livePrice), c: livePrice > previousClose ? "#00e87a" : "#ff4060" },
          { l: "Prev Close", v: fmt(pair, previousClose), c: "#8899aa" },
          { l: "Cambio %", v: market ? `${market.change_pct > 0 ? "+" : ""}${market.change_pct.toFixed(3)}%` : "-", c: market?.change_pct >= 0 ? "#00e87a" : "#ff4060" },
          { l: "High día", v: fmt(pair, market?.day_high), c: "#00e87a" },
          { l: "Low día", v: fmt(pair, market?.day_low), c: "#ff4060" },
          { l: "ATR(14)", v: market ? `${market.atr_14_pips.toFixed(1)} pips` : "-", c: "#ffaa00" },
          { l: "Vol real", v: market ? `${market.realized_vol_pct.toFixed(4)}%` : "-", c: "#00d4ff" },
        ]}
      />

      <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "5px", marginTop: "6px" }}>CONTEXTO API REAL</div>
      <MetricsCard
        rows={[
          { l: "Sesión", v: session?.label ?? "-", c: session?.is_overlap ? "#00e87a" : "#8899aa" },
          { l: "Evento Block", v: eventBlock?.active ? `Sí · ${eventBlock.reason}` : "No", c: eventBlock?.active ? "#ff4060" : "#00e87a" },
          { l: "Bias API", v: biasLabel(context?.bias), c: biasCol(biasLabel(context?.bias)) },
          { l: "Confidence", v: context ? `${context.confidence}%` : "-", c: scoreCol(context?.confidence ?? 50) },
          { l: "Tradeable", v: context?.tradeable ? "Sí" : "No", c: context?.tradeable ? "#00e87a" : "#ff4060" },
          { l: "News Risk", v: context?.news_risk ?? "-", c: context?.news_risk === "HIGH" ? "#ff4060" : context?.news_risk === "MEDIUM" ? "#ffaa00" : "#00e87a" },
          { l: "Score Adj", v: context?.score_adjust ?? "-", c: (context?.score_adjust ?? 0) >= 0 ? "#00e87a" : "#ff4060" },
          { l: "Macro Bias", v: context?.macro?.bias?.toFixed?.(3) ?? "-", c: "#00d4ff" },
          { l: "COT Bias", v: context?.cot_bias?.toFixed?.(3) ?? "-", c: "#8899aa" },
          { l: "Sent Bias", v: context?.sentiment_bias?.toFixed?.(3) ?? "-", c: "#8899aa" },
          { l: "Rango 1H", v: context ? `${context.expected_range_1h_pips.toFixed(1)} pips` : "-", c: "#ffaa00" },
        ]}
      />

      <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "5px", marginTop: "6px" }}>HORIZONTES API</div>
      <MetricsCard
        rows={[
          { l: "5m", v: tf5m ? `${biasLabel(tf5m.bias)} · ${tf5m.confidence}%` : "-", c: biasCol(biasLabel(tf5m?.bias)) },
          { l: "1H", v: tf1h ? `${biasLabel(tf1h.bias)} · ${tf1h.confidence}%` : "-", c: biasCol(biasLabel(tf1h?.bias)) },
          { l: "1D", v: tf1d ? `${biasLabel(tf1d.bias)} · ${tf1d.confidence}%` : "-", c: biasCol(biasLabel(tf1d?.bias)) },
        ]}
      />

      <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "5px", marginTop: "6px" }}>INDICADORES REALES</div>
      <MetricsCard
        rows={[
          { l: "RSI(14)", v: lastRSI.toFixed(1), c: rsiCol(lastRSI) },
          { l: "EMA9", v: fmt(pair, lastE9), c: "#ff9900" },
          { l: "EMA21", v: fmt(pair, lastE21), c: "#00ccff" },
          { l: "EMA50", v: fmt(pair, lastE50), c: "#cc44ff" },
          { l: "BB Upper", v: lastBB ? fmt(pair, lastBB.upper) : "-", c: "#0088cc" },
          { l: "BB Lower", v: lastBB ? fmt(pair, lastBB.lower) : "-", c: "#0088cc" },
          { l: "MACD Hist", v: lastMACD.toFixed(getDec(pair) + 2), c: lastMACD >= 0 ? "#00e87a" : "#ff4060" },
          { l: "Score Tec", v: `${techScore.score}/100`, c: scoreCol(techScore.score) },
        ]}
      />

      <div style={{ fontSize: "7px", letterSpacing: "2px", color: "#1a4060", marginBottom: "5px", marginTop: "6px" }}>PROVEEDORES</div>
      <div className="card">
        {Object.entries(providers).map(([name, provider]) => (
          <div key={name} className="sr">
            <span style={{ color: "#1a4060" }}>{name}</span>
            <span style={{ color: provider.ok ? "#00e87a" : "#ff4060", fontWeight: 600, fontSize: "10px" }}>
              {provider.ok ? "OK" : provider.detail}
            </span>
          </div>
        ))}
      </div>

      {predTime && (
        <div style={{ fontSize: "8px", color: "#1a3050", marginTop: "6px", textAlign: "center", lineHeight: "1.6" }}>
          Generada: {predTime.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </div>
      )}
    </div>
  );
}

export default function AtlasChart() {
  const [pair, setPair] = useState("EUR/USD");
  const [market, setMarket] = useState(null);
  const [context, setContext] = useState(null);
  const [mc, setMc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [countdown, setCountdown] = useState(null);
  const [predTime, setPredTime] = useState(null);
  const [showEMA, setShowEMA] = useState(true);
  const [showBB, setShowBB] = useState(true);
  const [showFib, setShowFib] = useState(false);
  const [showSR, setShowSR] = useState(true);
  const [predictionHorizon, setPredictionHorizon] = useState("1h");
  const timerRef = useRef(null);

  const symbol = pair.replace("/", "");

  useEffect(() => {
    let ignore = false;

    const load = async () => {
      if (!ignore) setLoading(true);
      try {
        const [marketData, contextData] = await Promise.all([
          fetchJson(`/market/${symbol}`),
          fetchJson(`/context/${symbol}`),
        ]);
        if (ignore) return;
        setMarket(marketData);
        setContext(contextData);
        setError("");
      } catch (err) {
        if (ignore) return;
        setError(err.message || "No se pudo cargar mercado/contexto real");
      } finally {
        if (!ignore) setLoading(false);
      }
    };

    load();
    const interval = setInterval(load, 60000);
    return () => {
      ignore = true;
      clearInterval(interval);
    };
  }, [symbol]);

  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const candles = useMemo(
    () =>
      (market?.candles || []).map((candle) => ({
        ...candle,
        t: new Date(candle.ts_utc),
      })),
    [market]
  );

  const closes = useMemo(() => candles.map((candle) => candle.c), [candles]);
  const ema9 = useMemo(() => calcEMA(closes, 9), [closes]);
  const ema21 = useMemo(() => calcEMA(closes, 21), [closes]);
  const ema50 = useMemo(() => calcEMA(closes, 50), [closes]);
  const bb = useMemo(() => calcBollinger(closes, 20, 2), [closes]);
  const rsiVals = useMemo(() => calcRSI(closes, 14), [closes]);
  const macdData = useMemo(() => calcMACD(closes), [closes]);
  const fibs = useMemo(() => calcFibonacci(candles), [candles]);
  const srZones = useMemo(() => detectSR(candles, 4), [candles]);
  const techScore = useMemo(() => calcTechScore(pair, closes, rsiVals, bb, macdData, ema9, ema21, ema50), [pair, closes, rsiVals, bb, macdData, ema9, ema21, ema50]);

  const lastRSI = rsiVals.filter(Boolean).pop() ?? 50;
  const lastMACD = macdData.hist.at(-1) ?? 0;
  const lastBB = bb.at(-1);
  const lastE9 = ema9.at(-1);
  const lastE21 = ema21.at(-1);
  const lastE50 = ema50.at(-1);

  const contextScore = useMemo(() => {
    if (!context) return 50;
    const baseAdjust = context.timeframe_1h?.score_adjust ?? context.score_adjust ?? 0;
    const baseConfidence = context.timeframe_1h?.confidence ?? context.confidence ?? 50;
    return clamp(Math.round(50 + baseAdjust * 3 + (baseConfidence - 50) * 0.5), 0, 100);
  }, [context]);

  const combinedScore = useMemo(() => clamp(Math.round(techScore.score * 0.55 + contextScore * 0.45), 0, 100), [techScore, contextScore]);

  const combinedBias = useMemo(() => {
    if (context?.bias) return biasLabel(context.bias);
    if (combinedScore >= 62) return "ALCISTA";
    if (combinedScore <= 38) return "BAJISTA";
    return "NEUTRO";
  }, [context, combinedScore]);

  const predict = () => {
    if (!context || !candles.length) return;
    setRunning(true);
    setTimeout(() => {
      const result = monteCarlo(pair, candles, context, combinedScore, predictionHorizon);
      setMc(result);
      setPredTime(new Date());
      setRunning(false);
      if (timerRef.current) clearInterval(timerRef.current);
      let seconds = result?.countdownSec ?? PREDICTION_HORIZONS[predictionHorizon].countdownSec;
      setCountdown(seconds);
      timerRef.current = setInterval(() => {
        seconds -= 1;
        setCountdown(seconds);
        if (seconds <= 0) {
          clearInterval(timerRef.current);
          setCountdown(null);
        }
      }, 1000);
    }, 300);
  };

  const changePredictionHorizon = (nextHorizon) => {
    setPredictionHorizon(nextHorizon);
    if (mc?.horizonKey !== nextHorizon) {
      setMc(null);
      setPredTime(null);
      setCountdown(null);
      if (timerRef.current) clearInterval(timerRef.current);
    }
  };

  const changePair = (nextPair) => {
    setPair(nextPair);
    setMarket(null);
    setContext(null);
    setMc(null);
    setPredTime(null);
    setCountdown(null);
    setError("");
    setLoading(true);
    if (timerRef.current) clearInterval(timerRef.current);
  };

  const fmtCountdown = (seconds) => {
    if (seconds == null) return "-";
    if (seconds >= 86400) {
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      return `${days}d ${hours}h`;
    }
    if (seconds >= 3600) {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      return `${hours}h ${String(minutes).padStart(2, "0")}m`;
    }
    const minutes = Math.floor(seconds / 60);
    const rem = seconds % 60;
    return `${minutes}:${String(rem).padStart(2, "0")}`;
  };

  const providers = context?.providers || {};
  const livePrice = market?.price;
  const previousClose = market?.previous_close;
  const layerToggles = [
    { lbl: "EMA", val: showEMA, set: setShowEMA },
    { lbl: "BB", val: showBB, set: setShowBB },
    { lbl: "FIB", val: showFib, set: setShowFib },
    { lbl: "S/R", val: showSR, set: setShowSR },
  ];

  return (
    <div style={{ fontFamily: "'IBM Plex Mono','Courier New',monospace", background: "#030b14", minHeight: "100vh", color: "#c8d8e8", display: "flex", flexDirection: "column" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=Orbitron:wght@700;900&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:#1a3a50}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.2}}
        @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
        @keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
        .logo{font-family:'Orbitron',monospace;font-size:17px;font-weight:900;letter-spacing:5px;background:linear-gradient(90deg,#00d4ff,#0044cc);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .pair-btn{background:#070d18;border:1px solid #0c1e2e;color:#3a6a88;font-family:'IBM Plex Mono',monospace;font-size:10px;padding:5px 10px;border-radius:2px;cursor:pointer;transition:.15s;letter-spacing:.5px}
        .pair-btn:hover{border-color:#1a4060;color:#66aacc}
        .pair-btn.act{background:#0c1e30;border-color:#00d4ff;color:#00d4ff}
        .tog{background:#070d18;border:1px solid #0c1e2e;color:#3a6a88;font-family:'IBM Plex Mono',monospace;font-size:9px;padding:4px 8px;border-radius:2px;cursor:pointer;transition:.15s}
        .tog:hover{border-color:#1a4060;color:#88bbcc}
        .tog.on{background:#0c2030;border-color:#0088cc;color:#00ccff}
        .pred-btn{background:linear-gradient(135deg,#005533,#002a1a);border:1px solid #008844;border-radius:3px;padding:9px 22px;color:#00ff88;font-family:'Orbitron',monospace;font-size:10px;letter-spacing:2px;cursor:pointer;transition:.2s}
        .pred-btn:hover{background:linear-gradient(135deg,#007744,#004422);box-shadow:0 0 12px rgba(0,255,136,.2)}
        .pred-btn:disabled{opacity:.35;cursor:not-allowed}
        .card{background:#070d18;border:1px solid #0c1e2e;border-radius:4px;padding:9px 11px;margin-bottom:6px}
        .sr{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #080f1a;font-size:10px}
        .metric{background:#070d18;border:1px solid #0c1e2e;border-radius:4px;padding:8px;text-align:center;flex:1}
        .mval{font-family:'Orbitron',monospace;font-size:15px;font-weight:800;margin-bottom:2px}
        .mlbl{font-size:7px;letter-spacing:1.5px;color:#1a4060}
        .sig-row{background:#070d18;border:1px solid #0c1e2e;border-radius:3px;padding:7px 10px;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center;animation:fadeIn .3s}
        .spin{animation:spin .9s linear infinite}
        .live-dot{width:5px;height:5px;border-radius:50%;background:#00e87a;box-shadow:0 0 5px #00e87a;animation:pulse 1.5s infinite}
      `}</style>

      <div style={{ background: "linear-gradient(180deg,#060e1a,#030b14)", borderBottom: "1px solid #0a1828", padding: "8px 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div className="logo">ATLAS</div>
          <div style={{ fontSize: "8px", color: "#1a4060", letterSpacing: "1px" }}>DATOS REALES · MERCADO + CONTEXTO MACRO + MONTE CARLO</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {countdown != null && (
            <div style={{ display: "flex", alignItems: "center", gap: "6px", background: "#0a1828", border: "1px solid #005533", borderRadius: "3px", padding: "4px 10px" }}>
              <div className="live-dot" />
              <span style={{ fontFamily: "'Orbitron',monospace", fontSize: "12px", color: "#00ff88" }}>{fmtCountdown(countdown)}</span>
              <span style={{ fontSize: "7px", color: "#006633", letterSpacing: "1px" }}>PRED ACTIVA</span>
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "9px", color: "#00e87a" }}>
            <div className="live-dot" />
            LIVE API
          </div>
          <div style={{ fontFamily: "'Orbitron',monospace", fontSize: "14px", fontWeight: 700, color: livePrice > previousClose ? "#00e87a" : "#ff4060" }}>
            {fmt(pair, livePrice)}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden", height: "calc(100vh - 46px)" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", padding: "10px 10px 10px 12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <div style={{ display: "flex", gap: "5px" }}>
              {PAIRS.map((candidate) => (
                <button key={candidate} className={`pair-btn${pair === candidate ? " act" : ""}`} onClick={() => changePair(candidate)}>
                  {candidate}
                </button>
              ))}
            </div>
            <LayerToggles toggles={layerToggles} />
          </div>

          {error && (
            <div style={{ marginBottom: "8px", background: "rgba(255,64,96,.08)", border: "1px solid rgba(255,64,96,.3)", borderRadius: "4px", padding: "10px", color: "#ff8098", fontSize: "11px" }}>
              {error}
            </div>
          )}

          <div style={{ position: "relative" }}>
            {loading && (
              <div style={{ position: "absolute", inset: 0, background: "rgba(3,11,20,.88)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", zIndex: 20, borderRadius: "6px" }}>
                <div style={{ width: "36px", height: "36px", border: "3px solid #0c1e2e", borderTop: "3px solid #00d4ff", borderRadius: "50%", marginBottom: "10px" }} className="spin" />
                <div style={{ fontFamily: "'Orbitron',monospace", fontSize: "10px", color: "#00d4ff", letterSpacing: "2px" }}>CARGANDO DATOS REALES</div>
              </div>
            )}
            <Chart pair={pair} candles={candles} mc={mc} ema9={ema9} ema21={ema21} ema50={ema50} bb={bb} srZones={srZones} fibs={fibs} showEMA={showEMA} showBB={showBB} showFib={showFib} showSR={showSR} />
          </div>

          <RSIChart rsiVals={rsiVals} />
          <MACDChart macdData={macdData} />
          <VolumeChart candles={candles} />

          <TechnicalSignalsPanel techScore={techScore} mc={mc} pair={pair} />
        </div>

        <SidebarPanel
          combinedBias={combinedBias}
          combinedScore={combinedScore}
          predict={predict}
          running={running}
          context={context}
          candles={candles}
          mc={mc}
          pair={pair}
          livePrice={livePrice}
          previousClose={previousClose}
          market={market}
          lastRSI={lastRSI}
          lastE9={lastE9}
          lastE21={lastE21}
          lastE50={lastE50}
          lastBB={lastBB}
          lastMACD={lastMACD}
          techScore={techScore}
          providers={providers}
          predTime={predTime}
          predictionHorizon={predictionHorizon}
          onChangePredictionHorizon={changePredictionHorizon}
        />
      </div>
    </div>
  );
}
