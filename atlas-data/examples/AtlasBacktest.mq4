//+------------------------------------------------------------------+
//| AtlasBacktest.mq4                                                |
//| ATLAS Strategy Tester — 6 timeframes sin API                    |
//| Usa indicadores MT4 nativos. Ejecutar en Strategy Tester M5.    |
//+------------------------------------------------------------------+
#property strict
#property copyright "ATLAS"
#property version   "1.0"
#property description "ATLAS Strategy Tester - 6TF alignment local"

//--- Inputs
extern double RiskPercent       = 1.0;
extern int    MagicNumber       = 270420;
extern int    MaxSlippage       = 30;
extern bool   AllowOnReal       = false;
extern double EmergencyStopPips = 25.0;
extern double TrailingStartPips = 10.0;
extern double TrailingStopPips  = 8.0;
extern double TrailingStepPips  = 2.0;
extern int    CountdownBars     = 12;    // barras M5 = 1H
extern int    MinAligned        = 4;     // de 6 TFs requeridos
extern double BiasTreshold      = 0.15;  // score min para ser direccional
extern double AtrSlMult         = 2.0;   // SL = ATR * mult
extern double AtrTpMult         = 3.0;   // TP = ATR * mult  -> RR 1.5

//--- Stats en tiempo real
int    g_totalTrades  = 0;
int    g_wins         = 0;
int    g_losses       = 0;
double g_grossProfit  = 0;
double g_grossLoss    = 0;
double g_totalPips    = 0;
double g_maxEquity    = 0;
double g_minEquity    = 9999999;
double g_peakBalance  = 0;
double g_maxDrawdown  = 0;
int    g_curLossStreak = 0;
int    g_maxLossStreak = 0;
int    g_tpCount      = 0;
int    g_slCount      = 0;
int    g_timeoutCount = 0;
int    g_flipCount    = 0;
datetime g_openTime   = 0;
string g_openDir      = "";


//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
double PipSize() {
   int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   double point = MarketInfo(Symbol(), MODE_POINT);
   if(digits == 3 || digits == 5) return(point * 10.0);
   return(point);
}

double AtrPips(int period = 14) {
   double atr = iATR(Symbol(), PERIOD_M5, period, 0);
   return(atr / PipSize());
}

//+------------------------------------------------------------------+
//| Score tecnico de un timeframe (EMA stack + RSI + pos vs MA50)   |
//| Devuelve valor en -1..+1                                         |
//+------------------------------------------------------------------+
double TfScore(string sym, int period) {
   double e9  = iMA(sym, period, 9,  0, MODE_EMA, PRICE_CLOSE, 0);
   double e21 = iMA(sym, period, 21, 0, MODE_EMA, PRICE_CLOSE, 0);
   double e50 = iMA(sym, period, 50, 0, MODE_EMA, PRICE_CLOSE, 0);
   double price = iClose(sym, period, 0);
   double rsi   = iRSI(sym, period, 14, PRICE_CLOSE, 0);

   double score = 0;

   // EMA stack (peso 0.45)
   if(e9 > e21 && e21 > e50)
      score += 0.45;
   else if(e9 < e21 && e21 < e50)
      score -= 0.45;
   else
      score += (e9 > e21 ? 1.0 : -1.0) * 0.15;

   // RSI (peso 0.30)
   if(rsi > 70)       score -= 0.24;
   else if(rsi < 30)  score += 0.24;
   else if(rsi > 55)  score += 0.12;
   else if(rsi < 45)  score -= 0.12;

   // Precio vs EMA50 (peso 0.25)
   double pct = (e50 > 0) ? (price - e50) / e50 : 0;
   double maSig = MathMax(-1.0, MathMin(1.0, pct * 150.0));
   score += maSig * 0.25;

   return(MathMax(-1.0, MathMin(1.0, score)));
}

//+------------------------------------------------------------------+
//| Bias de un TF: UP / DOWN / NEUTRAL                              |
//+------------------------------------------------------------------+
string TfBias(string sym, int period) {
   double s = TfScore(sym, period);
   if(s >  BiasTreshold) return("UP");
   if(s < -BiasTreshold) return("DOWN");
   return("NEUTRAL");
}

//+------------------------------------------------------------------+
//| Cuenta cuantos de los 6 TFs concuerdan con bias H1              |
//+------------------------------------------------------------------+
int AlignedCount(string sym) {
   string ref = TfBias(sym, PERIOD_H1);
   if(ref == "NEUTRAL") return(0);
   int periods[6] = {PERIOD_M5, PERIOD_M15, PERIOD_M30,
                     PERIOD_H1, PERIOD_H4,  PERIOD_D1};
   int cnt = 0;
   for(int i = 0; i < 6; i++) {
      if(TfBias(sym, periods[i]) == ref) cnt++;
   }
   return(cnt);
}

//+------------------------------------------------------------------+
//| Score compuesto para confirmacion local (tecnico M5)            |
//+------------------------------------------------------------------+
int CalcLocalScore() {
   string sym = Symbol();
   double e9  = iMA(sym, PERIOD_M5,  9, 0, MODE_EMA, PRICE_CLOSE, 0);
   double e21 = iMA(sym, PERIOD_M5, 21, 0, MODE_EMA, PRICE_CLOSE, 0);
   double e50 = iMA(sym, PERIOD_M5, 50, 0, MODE_EMA, PRICE_CLOSE, 0);
   double price = iClose(sym, PERIOD_M5, 0);
   double rsi  = iRSI(sym, PERIOD_M5, 14, PRICE_CLOSE, 0);
   double bbU  = iBands(sym, PERIOD_M5, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 0);
   double bbL  = iBands(sym, PERIOD_M5, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 0);
   double bbM  = iBands(sym, PERIOD_M5, 20, 2.0, 0, PRICE_CLOSE, MODE_MAIN,  0);
   double macd = iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_MAIN,   0)
               - iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
   double macdPrev = iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_MAIN,   1)
                   - iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);

   int score = 50;
   if(e9 > e21 && e21 > e50) score += 12; else if(e9 < e21 && e21 < e50) score -= 12;
   if(price > e50) score += 6; else score -= 6;
   if(rsi > 70) score -= 8; else if(rsi < 30) score += 8;
   else if(rsi > 55) score += 5; else if(rsi < 45) score -= 5;
   if(price > bbU) score -= 7; else if(price < bbL) score += 7;
   else if(price > bbM) score += 3; else score -= 3;
   if(macd > 0 && macd > macdPrev) score += 6; else if(macd < 0 && macd < macdPrev) score -= 6;

   if(score < 0) score = 0;
   if(score > 100) score = 100;
   return(score);
}

//+------------------------------------------------------------------+
//| Hurst exponent simplificado sobre closes M5 recientes           |
//+------------------------------------------------------------------+
double HurstSimple(int bars = 100) {
   if(iBars(Symbol(), PERIOD_M5) < bars) return(0.5);
   double closes[];
   ArrayResize(closes, bars);
   for(int i = 0; i < bars; i++)
      closes[i] = iClose(Symbol(), PERIOD_M5, bars - 1 - i);

   int lags[4] = {4, 8, 16, 32};
   double logRS[4], logL[4];
   int valid = 0;

   for(int li = 0; li < 4; li++) {
      int lag = lags[li];
      double rs_sum = 0; int rs_n = 0;
      for(int start = 0; start + lag <= bars; start += lag) {
         double mean = 0;
         for(int k = start; k < start + lag; k++) mean += closes[k];
         mean /= lag;
         double R = 0, cum = 0, S_sq = 0;
         double cum_min = 0, cum_max = 0;
         for(int k = start; k < start + lag; k++) {
            cum += closes[k] - mean;
            S_sq += MathPow(closes[k] - mean, 2);
            if(k == start) { cum_min = cum; cum_max = cum; }
            else { if(cum < cum_min) cum_min = cum; if(cum > cum_max) cum_max = cum; }
         }
         R = cum_max - cum_min;
         double S = MathSqrt(S_sq / lag);
         if(S > 0) { rs_sum += R / S; rs_n++; }
      }
      if(rs_n > 0) {
         logRS[valid] = MathLog(rs_sum / rs_n);
         logL[valid]  = MathLog((double)lag);
         valid++;
      }
   }
   if(valid < 2) return(0.5);

   double lx = 0, ly = 0;
   for(int i = 0; i < valid; i++) { lx += logL[i]; ly += logRS[i]; }
   lx /= valid; ly /= valid;
   double num = 0, den = 0;
   for(int i = 0; i < valid; i++) {
      num += (logL[i] - lx) * (logRS[i] - ly);
      den += MathPow(logL[i] - lx, 2);
   }
   return(den > 0 ? MathMax(0.1, MathMin(0.9, num / den)) : 0.5);
}

//+------------------------------------------------------------------+
//| Volatilidad: LOW / NORMAL / HIGH                                |
//+------------------------------------------------------------------+
string VolRegime(int period = 50) {
   double curAtr = iATR(Symbol(), PERIOD_M5, 14, 0) / PipSize();
   double vals[];
   ArrayResize(vals, period);
   for(int i = 0; i < period; i++)
      vals[i] = iATR(Symbol(), PERIOD_M5, 14, i) / PipSize();
   ArraySort(vals);
   double p25 = vals[(int)(period * 0.25)];
   double p75 = vals[(int)(period * 0.75)];
   if(curAtr > p75 * 1.3) return("HIGH");
   if(curAtr < p25 * 0.8) return("LOW");
   return("NORMAL");
}

//+------------------------------------------------------------------+
//| Regresion lineal: devuelve (slope_pips_por_barra, R2)           |
//+------------------------------------------------------------------+
void LinReg(int period, double &slope_pips, double &r2) {
   slope_pips = 0; r2 = 0;
   if(iBars(Symbol(), PERIOD_M5) < period + 1) return;
   double xm = (period - 1) / 2.0;
   double ym = 0;
   for(int i = 0; i < period; i++) ym += iClose(Symbol(), PERIOD_M5, period - 1 - i);
   ym /= period;
   double xy = 0, xx = 0, yy = 0;
   for(int i = 0; i < period; i++) {
      double y = iClose(Symbol(), PERIOD_M5, period - 1 - i);
      xy += (i - xm) * (y - ym);
      xx += MathPow(i - xm, 2);
      yy += MathPow(y - ym, 2);
   }
   if(xx == 0) return;
   double rawSlope = xy / xx;
   slope_pips = rawSlope / PipSize();
   r2 = (yy > 0) ? (xy * xy) / (xx * yy) : 0;
}

//+------------------------------------------------------------------+
//| Gestion de trailing stop                                         |
//+------------------------------------------------------------------+
void ManageTrailing(int ticket) {
   if(TrailingStopPips <= 0 || TrailingStartPips <= 0) return;
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
   double pip = PipSize();
   int    type = OrderType();
   if(type != OP_BUY && type != OP_SELL) return;
   double current = (type == OP_BUY) ? Bid : Ask;
   double open    = OrderOpenPrice();
   double profitPips = (type == OP_BUY) ? (current - open) / pip : (open - current) / pip;
   if(profitPips < TrailingStartPips) return;
   double desiredSl = (type == OP_BUY)
                      ? current - TrailingStopPips * pip
                      : current + TrailingStopPips * pip;
   double minStop = MarketInfo(Symbol(), MODE_STOPLEVEL) * MarketInfo(Symbol(), MODE_POINT);
   if(type == OP_BUY  && current - desiredSl < minStop) desiredSl = current - minStop;
   if(type == OP_SELL && desiredSl - current < minStop) desiredSl = current + minStop;
   desiredSl = NormalizeDouble(desiredSl, (int)MarketInfo(Symbol(), MODE_DIGITS));
   double oldSl = OrderStopLoss();
   bool improve = (type == OP_BUY)
                  ? (oldSl <= 0 || desiredSl > oldSl + TrailingStepPips * pip)
                  : (oldSl <= 0 || desiredSl < oldSl - TrailingStepPips * pip);
   if(improve)
      OrderModify(ticket, open, desiredSl, OrderTakeProfit(), 0, clrDodgerBlue);
}

//+------------------------------------------------------------------+
//| Calcular lotes por riesgo                                        |
//+------------------------------------------------------------------+
double CalcLots(double price, double sl) {
   double riskMoney  = AccountBalance() * RiskPercent / 100.0;
   double slDist     = MathAbs(price - sl);
   if(slDist <= 0) return(0);
   double tickVal  = MarketInfo(Symbol(), MODE_TICKVALUE);
   double tickSize = MarketInfo(Symbol(), MODE_TICKSIZE);
   if(tickSize <= 0 || tickVal <= 0) return(0);
   double lossPerLot = (slDist / tickSize) * tickVal;
   if(lossPerLot <= 0) return(0);
   double lots = riskMoney / lossPerLot;
   double minLot = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot = MarketInfo(Symbol(), MODE_MAXLOT);
   double step   = MarketInfo(Symbol(), MODE_LOTSTEP);
   if(step <= 0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < minLot) return(0);
   if(lots > maxLot) lots = maxLot;
   return(lots);
}

//+------------------------------------------------------------------+
//| Actualizar estadísticas en el comentario del gráfico            |
//+------------------------------------------------------------------+
void UpdateStats() {
   double wr    = (g_totalTrades > 0) ? (double)g_wins / g_totalTrades * 100.0 : 0;
   double pf    = (g_grossLoss > 0)   ? g_grossProfit / g_grossLoss : 0;
   double avgW  = (g_wins   > 0) ? g_grossProfit / g_wins   : 0;
   double avgL  = (g_losses > 0) ? g_grossLoss   / g_losses : 0;
   double expect = (g_totalTrades > 0) ? g_totalPips / g_totalTrades : 0;

   double hurst = HurstSimple();
   string hurstRegime = (hurst > 0.6) ? "TREND" : ((hurst < 0.4) ? "REVERT" : "RANDOM");
   double slope = 0, r2 = 0;
   LinReg(20, slope, r2);
   string volR = VolRegime();

   Comment(
      "ATLAS Strategy Tester — 6 Timeframes\n",
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
      "Operaciones:     ", g_totalTrades, "\n",
      "Win rate:        ", DoubleToString(wr, 1), "%\n",
      "Profit factor:   ", DoubleToString(pf, 2), "\n",
      "Total pips:      ", DoubleToString(g_totalPips, 1), "\n",
      "Expectancy:      ", DoubleToString(expect, 2), " pips/op\n",
      "Avg win:         ", DoubleToString(avgW, 1), " pips\n",
      "Avg loss:        ", DoubleToString(avgL, 1), " pips\n",
      "Max DD:          ", DoubleToString(g_maxDrawdown, 1), " pips\n",
      "Racha pérd.:     ", g_maxLossStreak, "\n",
      "TP/SL/TIMEOUT:   ", g_tpCount, "/", g_slCount, "/", g_timeoutCount, "\n",
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
      "Hurst:  ", DoubleToString(hurst, 3), " (", hurstRegime, ")\n",
      "LinReg: ", DoubleToString(slope, 3), " pips/barra  R2=", DoubleToString(r2, 2), "\n",
      "Vol:    ", volR, "\n",
      "Alineados: ", AlignedCount(Symbol()), "/6  MinReq=", MinAligned
   );
}

//+------------------------------------------------------------------+
//| Registrar cierre de operacion                                    |
//+------------------------------------------------------------------+
void RecordClose(int ticket, string reason) {
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
   double pnlPips = 0;
   if(OrderType() == OP_BUY)
      pnlPips = (Bid - OrderOpenPrice()) / PipSize();
   else
      pnlPips = (OrderOpenPrice() - Ask) / PipSize();

   g_totalTrades++;
   g_totalPips += pnlPips;
   if(pnlPips > 0) {
      g_wins++;
      g_grossProfit += pnlPips;
      g_curLossStreak = 0;
   } else {
      g_losses++;
      g_grossLoss += MathAbs(pnlPips);
      g_curLossStreak++;
      if(g_curLossStreak > g_maxLossStreak) g_maxLossStreak = g_curLossStreak;
   }

   // Drawdown
   double equity = AccountEquity();
   if(equity > g_maxEquity) { g_maxEquity = equity; g_peakBalance = equity; }
   double dd = g_peakBalance - equity;
   if(dd > g_maxDrawdown) g_maxDrawdown = dd;

   if(reason == "TP")      g_tpCount++;
   else if(reason == "SL") g_slCount++;
   else if(reason == "TIMEOUT") g_timeoutCount++;
   else                    g_flipCount++;

   PrintFormat("ATLAS CLOSE [%s] pnl=%.1f pips ticket=%d", reason, pnlPips, ticket);
}

//+------------------------------------------------------------------+
//| Encontrar orden activa del EA                                    |
//+------------------------------------------------------------------+
int FindMyOrder() {
   for(int k = OrdersTotal() - 1; k >= 0; k--) {
      if(!OrderSelect(k, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() == MagicNumber && OrderSymbol() == Symbol())
         return(OrderTicket());
   }
   return(-1);
}

//+------------------------------------------------------------------+
//| Cerrar orden                                                     |
//+------------------------------------------------------------------+
void CloseOrder(int ticket, string reason) {
   RecordClose(ticket, reason);
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
   double price = (OrderType() == OP_BUY) ? Bid : Ask;
   OrderClose(ticket, OrderLots(), price, MaxSlippage, clrYellow);
}

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit() {
   if(!IsDemo() && !IsOptimization() && !AllowOnReal) {
      Alert("AtlasBacktest: solo demo / Strategy Tester");
      return(INIT_FAILED);
   }
   g_peakBalance = AccountBalance();
   PrintFormat("AtlasBacktest init sym=%s TF=M5 minAligned=%d biasThresh=%.2f",
               Symbol(), MinAligned, BiasTreshold);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| OnDeinit — imprime resumen final en el log                      |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   Comment("");
   if(g_totalTrades == 0) { Print("AtlasBacktest: sin operaciones"); return; }

   double wr = (double)g_wins / g_totalTrades * 100.0;
   double pf = (g_grossLoss > 0) ? g_grossProfit / g_grossLoss : 0;
   double ex = g_totalPips / g_totalTrades;

   PrintFormat("=== ATLAS BACKTEST RESUMEN ===");
   PrintFormat("Operaciones:      %d", g_totalTrades);
   PrintFormat("Win rate:         %.1f%%", wr);
   PrintFormat("Profit factor:    %.2f", pf);
   PrintFormat("Total pips:       %.1f", g_totalPips);
   PrintFormat("Expectancy:       %.2f pips/op", ex);
   PrintFormat("Avg win:          %.1f pips", (g_wins > 0 ? g_grossProfit / g_wins : 0));
   PrintFormat("Avg loss:         %.1f pips", (g_losses > 0 ? g_grossLoss / g_losses : 0));
   PrintFormat("Max loss streak:  %d", g_maxLossStreak);
   PrintFormat("TP / SL / TIMEOUT / FLIP: %d / %d / %d / %d",
               g_tpCount, g_slCount, g_timeoutCount, g_flipCount);
}

//+------------------------------------------------------------------+
//| OnTick                                                           |
//+------------------------------------------------------------------+
void OnTick() {
   // Calcular señal actual
   int aligned = AlignedCount(Symbol());
   string ref  = TfBias(Symbol(), PERIOD_H1);
   bool   signal = (aligned >= MinAligned && ref != "NEUTRAL");
   bool   goLong  = signal && (ref == "UP");
   bool   goShort = signal && (ref == "DOWN");

   int ticket = FindMyOrder();

   // Gestionar posición abierta
   if(ticket >= 0) {
      ManageTrailing(ticket);

      // Cierre por tiempo
      if(OrderSelect(ticket, SELECT_BY_TICKET)) {
         int elapsed = (int)((TimeCurrent() - OrderOpenTime()) / PeriodSeconds(PERIOD_M5));
         if(elapsed >= CountdownBars) {
            CloseOrder(ticket, "TIMEOUT");
            UpdateStats();
            return;
         }
      }

      // Cierre por señal contraria
      if(OrderSelect(ticket, SELECT_BY_TICKET)) {
         int type = OrderType();
         bool opposite = (type == OP_BUY && goShort) || (type == OP_SELL && goLong);
         if(opposite) {
            CloseOrder(ticket, "FLIP");
            UpdateStats();
         }
      }
      UpdateStats();
      return;
   }

   // Nueva entrada
   if(!goLong && !goShort) { UpdateStats(); return; }

   double atrPips = AtrPips(14);
   if(atrPips <= 0) { UpdateStats(); return; }
   double atrPrice = atrPips * PipSize();
   int    digits   = (int)MarketInfo(Symbol(), MODE_DIGITS);

   double price, sl, tp;
   int    opType;

   if(goLong) {
      price = Ask;
      sl = price - atrPrice * AtrSlMult;
      tp = price + atrPrice * AtrTpMult;
      opType = OP_BUY;
   } else {
      price = Bid;
      sl = price + atrPrice * AtrSlMult;
      tp = price - atrPrice * AtrTpMult;
      opType = OP_SELL;
   }

   // Emergency stop
   if(EmergencyStopPips > 0) {
      double maxDist = EmergencyStopPips * PipSize();
      double minStop = MarketInfo(Symbol(), MODE_STOPLEVEL) * MarketInfo(Symbol(), MODE_POINT);
      if(opType == OP_BUY) {
         if(price - sl > maxDist) sl = price - maxDist;
         if(price - sl < minStop) sl = price - minStop;
      } else {
         if(sl - price > maxDist) sl = price + maxDist;
         if(sl - price < minStop) sl = price + minStop;
      }
   }

   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);

   double lots = CalcLots(price, sl);
   if(lots <= 0) { UpdateStats(); return; }

   // Score local para el comentario
   int localScore = CalcLocalScore();
   double hurst   = HurstSimple();
   string cm = StringFormat("ATLAS6TF a=%d/6 score=%d H=%.2f", aligned, localScore, hurst);

   int t = OrderSend(Symbol(), opType, lots, NormalizeDouble(price, digits),
                     MaxSlippage, sl, tp, cm, MagicNumber, 0,
                     goLong ? clrLime : clrTomato);
   if(t > 0) {
      g_openTime = TimeCurrent();
      g_openDir  = goLong ? "UP" : "DOWN";
      PrintFormat("ATLAS OPEN %s lots=%.2f price=%.5f sl=%.5f tp=%.5f aligned=%d/6 score=%d",
                  goLong ? "BUY" : "SELL", lots, price, sl, tp, aligned, localScore);
   }

   UpdateStats();
}

//+------------------------------------------------------------------+
//| OnTester — métricas custom visibles en el Report del Tester     |
//+------------------------------------------------------------------+
double OnTester() {
   if(g_totalTrades == 0) return(0.0);
   double wr = (double)g_wins / g_totalTrades * 100.0;
   double pf = (g_grossLoss > 0) ? g_grossProfit / g_grossLoss : 0;
   // Métrica de optimización: Profit Factor * Win Rate / 100
   return(pf * wr / 100.0);
}
