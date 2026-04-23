#property strict
#property copyright "ATLAS"
#property version   "1.12"
#property description "ATLAS - tecnico + Monte Carlo + contexto MT4/API"

extern string  SymbolSuffix     = "";
extern int     MagicNumber      = 270419;
extern double  RiskPercent      = 1.0;
extern int     OperateThreshold = 62;
extern int     MinConfPercent   = 55;
extern int     MinApiConfidence = 55;
extern string  TradeHorizon     = "1H";
extern int     CountdownSec     = 0;
extern int     EvalEverySec     = 60;
extern int     MC_Paths         = 400;
extern int     MaxSlippage      = 30;
extern bool    AllowOnReal      = false;
extern bool    RequireTripleAlignment = true;
extern bool    RequireLocalConfirmation = false;
extern bool    CloseOnApiDisagreement = true;
extern bool    ShowStatusPanel = true;
extern double  EmergencyStopPips = 25.0;
extern double  TrailingStartPips = 10.0;
extern double  TrailingStopPips  = 8.0;
extern double  TrailingStepPips  = 2.0;

extern bool    UseDataApi       = true;
extern bool    RequireApiForTrading = true;
extern string  DataApiUrl       = "http://127.0.0.1:8000/";
extern string  BackupDataApiUrl = "";
extern string  DataApiPath      = "";
extern bool    UseFlatApiUrl    = true;
extern string  DataApiKey       = "";
extern int     ApiTimeoutMs     = 4000;

extern int  COT_EURUSD = 42800;   extern int RET_EURUSD = 38;
extern int  COT_GBPUSD =-18200;   extern int RET_GBPUSD = 55;
extern int  COT_USDJPY = 61500;   extern int RET_USDJPY = 29;
extern int  COT_XAUUSD = 94200;   extern int RET_XAUUSD = 71;
extern int  COT_AUDUSD =-22400;   extern int RET_AUDUSD = 61;
extern int  COT_USDCAD = 14600;   extern int RET_USDCAD = 35;
extern int  COT_USDCHF = -9800;   extern int RET_USDCHF = 44;

string   PAIRS[7] = {"EURUSD","GBPUSD","USDJPY","XAUUSD","AUDUSD","USDCAD","USDCHF"};
datetime lastEval[7];
double   cotOverride[7];
datetime lastApiOkTime = 0;
datetime lastApiFailTime = 0;
string   lastApiError = "";
int      lastAlignedCount = 0;
int      lastCheckedCount = 0;

string NormalizeHorizon() {
   string horizon = TradeHorizon;
   StringToUpper(horizon);
   if(horizon != "5M" && horizon != "1H" && horizon != "1D")
      horizon = "1H";
   return(horizon);
}

int HorizonCountdownSec() {
   string horizon = NormalizeHorizon();
   if(horizon == "5M") return(300);
   if(horizon == "1D") return(86400);
   return(3600);
}

int EffectiveCountdownSec() {
   if(CountdownSec > 0) return(CountdownSec);
   return(HorizonCountdownSec());
}

int HorizonSteps() {
   string horizon = NormalizeHorizon();
   if(horizon == "5M") return(1);
   if(horizon == "1D") return(24);
   return(12);
}

double HorizonDt() {
   if(NormalizeHorizon() == "5M") return(1.0 / 288.0);
   return(1.0 / 24.0);
}

double PipSize(string sym) {
   double point = MarketInfo(sym, MODE_POINT);
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   if(digits == 3 || digits == 5) return(point * 10.0);
   return(point);
}

double StopLevelDistance(string sym) {
   return(MarketInfo(sym, MODE_STOPLEVEL) * MarketInfo(sym, MODE_POINT));
}

bool TripleAligned(string b5m, string b1h, string b1d, string &bias) {
   bias = "NEUTRAL";
   if(b5m == b1h && b1h == b1d && b5m != "NEUTRAL") {
      bias = b5m;
      return(true);
   }
   return(false);
}

void ApplyEmergencyStop(string sym, int dir, double price, double &sl) {
   if(EmergencyStopPips <= 0) return;
   double maxDistance = EmergencyStopPips * PipSize(sym);
   double emergencySl = (dir > 0) ? price - maxDistance : price + maxDistance;
   double minStop = StopLevelDistance(sym);

   if(dir > 0) {
      if(sl <= 0 || price - sl > maxDistance) sl = emergencySl;
      if(price - sl < minStop) sl = price - minStop;
   } else {
      if(sl <= 0 || sl - price > maxDistance) sl = emergencySl;
      if(sl - price < minStop) sl = price + minStop;
   }
}

void ManageTrailingStop(int ticket) {
   if(TrailingStopPips <= 0 || TrailingStartPips <= 0) return;
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;

   string sym = OrderSymbol();
   double pip = PipSize(sym);
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   int type = OrderType();
   if(type != OP_BUY && type != OP_SELL) return;

   double current = (type == OP_BUY) ? MarketInfo(sym, MODE_BID) : MarketInfo(sym, MODE_ASK);
   double open = OrderOpenPrice();
   double profitPips = (type == OP_BUY) ? (current - open) / pip : (open - current) / pip;
   if(profitPips < TrailingStartPips) return;

   double desiredSl = (type == OP_BUY)
                      ? current - TrailingStopPips * pip
                      : current + TrailingStopPips * pip;
   double minStop = StopLevelDistance(sym);
   if(type == OP_BUY && current - desiredSl < minStop) desiredSl = current - minStop;
   if(type == OP_SELL && desiredSl - current < minStop) desiredSl = current + minStop;
   desiredSl = NormalizeDouble(desiredSl, digits);

   double oldSl = OrderStopLoss();
   bool improve = false;
   if(type == OP_BUY)
      improve = (oldSl <= 0 || desiredSl > oldSl + TrailingStepPips * pip);
   else
      improve = (oldSl <= 0 || desiredSl < oldSl - TrailingStepPips * pip);
   if(!improve) return;

   bool ok = OrderModify(ticket, open, desiredSl, OrderTakeProfit(), 0, clrDodgerBlue);
   if(!ok)
      PrintFormat("ATLAS trailing FAIL %s ticket=%d err=%d", sym, ticket, GetLastError());
}

string TimeAgo(datetime ts) {
   if(ts <= 0) return("nunca");
   int sec = (int)(TimeCurrent() - ts);
   if(sec < 0) sec = 0;
   if(sec < 60) return(StringFormat("%ds", sec));
   if(sec < 3600) return(StringFormat("%dm", sec / 60));
   return(StringFormat("%dh %dm", sec / 3600, (sec % 3600) / 60));
}

void UpdateStatusPanel() {
   if(!ShowStatusPanel) {
      Comment("");
      return;
   }

   bool connected = (lastApiOkTime > 0 && (lastApiFailTime == 0 || lastApiOkTime >= lastApiFailTime));
   string apiState = connected ? "CONECTADA" : "NO CONECTADA";
   string mode = RequireApiForTrading ? "fail-closed" : "degradado";
   string operating = connected ? "SI" : (RequireApiForTrading ? "NO" : "DEGRADADO");

   Comment(
      "ATLAS API: ", apiState, "\n",
      "Funcionando: ", operating, " | modo=", mode, "\n",
      "Ultimo OK: ", TimeAgo(lastApiOkTime), " | Ultimo fallo: ", TimeAgo(lastApiFailTime), "\n",
      "Pares alineados: ", lastAlignedCount, "/", lastCheckedCount, "\n",
      "Estrategia: 5M = 1H = 1D | horizonte=", NormalizeHorizon(), "\n",
      "Riesgo: SL emergencia=", DoubleToString(EmergencyStopPips, 1),
      " pips | trailing=", DoubleToString(TrailingStopPips, 1), " pips\n",
      "Ultimo error: ", lastApiError
   );
}

int OnInit() {
   if(!IsDemo() && !AllowOnReal) {
      Alert("ATLAS: cuenta REAL detectada y AllowOnReal=false. EA detenido.");
      return(INIT_FAILED);
   }
   ArrayInitialize(lastEval, 0);
   ArrayInitialize(cotOverride, 0);
   MathSrand((int)TimeLocal());
   PrintFormat("ATLAS iniciado pares=7 riesgo=%.2f%% sufijo='%s' demo=%s horizonte=%s",
               RiskPercent, SymbolSuffix, IsDemo() ? "si" : "no", NormalizeHorizon());
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {
   Comment("");
   PrintFormat("ATLAS detenido (reason=%d)", reason);
}

void OnTick() {
   int alignedCount = 0;
   int checkedCount = 0;
   for(int i = 0; i < 7; i++) {
      string sym = PAIRS[i] + SymbolSuffix;
      if(MarketInfo(sym, MODE_BID) <= 0) continue;
      bool pairAligned = false;
      bool pairChecked = false;
      ManagePair(i, sym, pairAligned, pairChecked);
      if(pairChecked) checkedCount++;
      if(pairAligned) alignedCount++;
   }
   if(checkedCount > 0) {
      lastCheckedCount = checkedCount;
      lastAlignedCount = alignedCount;
   }
   UpdateStatusPanel();
}

int FindMyOrder(string sym) {
   for(int k = OrdersTotal() - 1; k >= 0; k--) {
      if(!OrderSelect(k, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() == MagicNumber && OrderSymbol() == sym)
         return(OrderTicket());
   }
   return(-1);
}

void CloseMyOrder(int ticket, string reason) {
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
   double price = (OrderType() == OP_BUY)
                  ? MarketInfo(OrderSymbol(), MODE_BID)
                  : MarketInfo(OrderSymbol(), MODE_ASK);
   bool ok = OrderClose(ticket, OrderLots(), price, MaxSlippage, clrYellow);
   PrintFormat("ATLAS cierre [%s] %s ticket=%d ok=%s err=%d",
               reason, OrderSymbol(), ticket, ok ? "si" : "no",
               ok ? 0 : GetLastError());
}

void ManagePair(int i, string sym, bool &pairAligned, bool &pairChecked) {
   pairAligned = false;
   pairChecked = false;
   int ticket = FindMyOrder(sym);

   if(ticket >= 0) {
      ManageTrailingStop(ticket);
      if(OrderSelect(ticket, SELECT_BY_TICKET)) {
         if(TimeCurrent() - OrderOpenTime() >= EffectiveCountdownSec()) {
            CloseMyOrder(ticket, NormalizeHorizon());
            return;
         }
      }
      if(UseDataApi && CloseOnApiDisagreement && TimeCurrent() - lastEval[i] >= EvalEverySec) {
         lastEval[i] = TimeCurrent();
         int closeAdj = 0, closeConf = 0;
         string closeRisk = "", closeBias = "NEUTRAL";
         string b5m = "NEUTRAL", b1h = "NEUTRAL", b1d = "NEUTRAL";
         int c5m = 0, c1h = 0, c1d = 0;
         bool closeBlock = false, closeTradeable = true;
         double closeRange = 0.0;
         bool ok = FetchContext(PAIRS[i], closeAdj, closeRisk, closeBlock, closeBias, closeConf,
                                closeTradeable, closeRange, b5m, b1h, b1d, c5m, c1h, c1d);
         if(ok) {
            pairChecked = true;
            string alignedBias = "NEUTRAL";
            bool aligned = TripleAligned(b5m, b1h, b1d, alignedBias);
            pairAligned = aligned;
            int type = OrderType();
            bool opposite = (type == OP_BUY && alignedBias == "DOWN") || (type == OP_SELL && alignedBias == "UP");
            if(closeBlock || !aligned || opposite) {
               CloseMyOrder(ticket, closeBlock ? "API_BLOCK" : "API_DISAGREE");
            }
         } else if(RequireApiForTrading) {
            CloseMyOrder(ticket, "API_LOST");
         }
      }
      return;
   }

   if(TimeCurrent() - lastEval[i] < EvalEverySec) return;
   lastEval[i] = TimeCurrent();

   int    apiAdj = 0;
   string newsRisk = "";
   bool   blockTrading = false;
   string apiBias = "NEUTRAL";
   string bias5m = "NEUTRAL";
   string bias1h = "NEUTRAL";
   string bias1d = "NEUTRAL";
   int    apiConfidence = 0;
   int    conf5m = 0;
   int    conf1h = 0;
   int    conf1d = 0;
   bool   apiTradeable = true;
   double apiRangePips = 0.0;
   bool   apiAvailable = true;

   if(UseDataApi)
      apiAvailable = FetchContext(PAIRS[i], apiAdj, newsRisk, blockTrading, apiBias, apiConfidence,
                                  apiTradeable, apiRangePips, bias5m, bias1h, bias1d, conf5m, conf1h, conf1d);
   if(UseDataApi && apiAvailable)
      pairChecked = true;

   if(UseDataApi && !apiAvailable) {
      if(RequireApiForTrading) {
         PrintFormat("ATLAS API no disponible %s: modo fail-closed", sym);
         return;
      }
      PrintFormat("ATLAS API no disponible %s: continuo en modo degradado", sym);
   }

   if(apiAvailable && (blockTrading || !apiTradeable)) {
      PrintFormat("ATLAS bloqueo externo %s bias=%s conf=%d risk=%s",
                  sym, apiBias, apiConfidence, newsRisk);
      return;
   }

   if(UseDataApi && apiAvailable && RequireTripleAlignment) {
      string alignedBias = "NEUTRAL";
      if(!TripleAligned(bias5m, bias1h, bias1d, alignedBias)) {
         PrintFormat("ATLAS sin alineacion triple %s 5M=%s 1H=%s 1D=%s",
                     sym, bias5m, bias1h, bias1d);
         return;
      }
      pairAligned = true;
      apiBias = alignedBias;
      apiConfidence = (int)MathMin(conf5m, MathMin(conf1h, conf1d));
      apiTradeable = true;
   }

   int techScore = CalcTechScore(sym);
   int confScore = CalcConfluenceScore(i, sym);
   int combined  = (int)MathRound(confScore * 0.40 + techScore * 0.60) + apiAdj;
   if(combined < 0)   combined = 0;
   if(combined > 100) combined = 100;

   bool goLong  = (combined >= OperateThreshold);
   bool goShort = (combined <= 100 - OperateThreshold);

   if(UseDataApi && apiAvailable && RequireTripleAlignment && !RequireLocalConfirmation) {
      goLong = (apiBias == "UP");
      goShort = (apiBias == "DOWN");
      if(goLong && combined < apiConfidence) combined = apiConfidence;
      if(goShort && combined > 100 - apiConfidence) combined = 100 - apiConfidence;
   }

   if(UseDataApi && apiAvailable) {
      if(apiConfidence < MinApiConfidence) return;
      if(apiBias == "UP") goShort = false;
      else if(apiBias == "DOWN") goLong = false;
      else {
         goLong = false;
         goShort = false;
      }
   }

   if(!goLong && !goShort) return;

   int    dir   = goLong ? 1 : -1;
   double price = goLong ? MarketInfo(sym, MODE_ASK) : MarketInfo(sym, MODE_BID);

   double tp = 0, sl = 0;
   double conf = MonteCarlo(sym, price, combined, dir, tp, sl);
   if(conf < 0) return;
   if(conf < MinConfPercent) return;

   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   ApplyEmergencyStop(sym, dir, price, sl);
   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);

   double lots = CalcLots(sym, price, sl);
   if(lots <= 0) {
      PrintFormat("ATLAS %s: lotes=0, omito", sym);
      return;
   }

   int type   = goLong ? OP_BUY : OP_SELL;
   string cm  = StringFormat("ATLAS %s s=%d c=%.0f api=%s/%d r=%.1f",
                             NormalizeHorizon(), combined, conf, apiBias, apiConfidence, apiRangePips);
   color col  = goLong ? clrLime : clrTomato;

   int t = OrderSend(sym, type, lots, NormalizeDouble(price, digits),
                     MaxSlippage, sl, tp, cm, MagicNumber, 0, col);
   if(t < 0) {
      PrintFormat("ATLAS OrderSend FAIL %s err=%d lots=%.2f price=%.5f sl=%.5f tp=%.5f",
                  sym, GetLastError(), lots, price, sl, tp);
   } else {
      PrintFormat("ATLAS abre %s %s lots=%.2f @ %.5f sl=%.5f tp=%.5f score=%d conf=%.0f%% api=%s/%d",
                  goLong ? "BUY" : "SELL", sym, lots, price, sl, tp, combined, conf, apiBias, apiConfidence);
   }
}

int CalcTechScore(string sym) {
   double e9   = iMA(sym, PERIOD_M5,  9, 0, MODE_EMA, PRICE_CLOSE, 0);
   double e21  = iMA(sym, PERIOD_M5, 21, 0, MODE_EMA, PRICE_CLOSE, 0);
   double e50  = iMA(sym, PERIOD_M5, 50, 0, MODE_EMA, PRICE_CLOSE, 0);
   double price= iClose(sym, PERIOD_M5, 0);
   double rsi  = iRSI(sym, PERIOD_M5, 14, PRICE_CLOSE, 0);
   double bbU  = iBands(sym, PERIOD_M5, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 0);
   double bbL  = iBands(sym, PERIOD_M5, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 0);
   double bbM  = iBands(sym, PERIOD_M5, 20, 2.0, 0, PRICE_CLOSE, MODE_MAIN,  0);
   double mh0  = iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_MAIN,   0)
               - iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
   double mh1  = iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_MAIN,   1)
               - iMACD(sym, PERIOD_M5, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
   double c5   = iClose(sym, PERIOD_M5, 5);
   double roc5 = (c5 != 0) ? (price - c5) / c5 * 100.0 : 0;

   int score = 50;
   if(e9 > e21 && e21 > e50) score += 12;
   else if(e9 < e21 && e21 < e50) score -= 12;
   if(price > e50) score += 6; else score -= 6;
   if(rsi > 70) score -= 8;
   else if(rsi < 30) score += 8;
   else if(rsi > 55) score += 5;
   else if(rsi < 45) score -= 5;
   if(price > bbU) score -= 7;
   else if(price < bbL) score += 7;
   else if(price > bbM) score += 3;
   else score -= 3;
   if(mh0 > 0 && mh0 > mh1) score += 6;
   else if(mh0 < 0 && mh0 < mh1) score -= 6;
   else if(mh0 > 0) score += 2;
   else score -= 2;
   if(MathAbs(roc5) > 0.3) score += (roc5 > 0 ? 4 : -4);
   if(score < 0) score = 0;
   if(score > 100) score = 100;
   return(score);
}

int CalcConfluenceScore(int i, string sym) {
   double r15 = iRSI(sym, PERIOD_M15, 14, PRICE_CLOSE, 0);
   double r1h = iRSI(sym, PERIOD_H1,  14, PRICE_CLOSE, 0);
   double r4h = iRSI(sym, PERIOD_H4,  14, PRICE_CLOSE, 0);
   double rd1 = iRSI(sym, PERIOD_D1,  14, PRICE_CLOSE, 0);
   double rsiAvg = (r15 + r1h + r4h + rd1) / 4.0;

   int cot, ret;
   GetCotRetail(i, cot, ret);
   if(MathAbs(cotOverride[i]) > 0.5) cot = (int)cotOverride[i];

   double s = 50.0;
   s += (rsiAvg - 50.0) * 0.6;
   s += (cot / 10000.0) * 1.5;
   s += (50.0 - ret) * 0.25;

   int v = (int)MathRound(s);
   if(v < 0) v = 0;
   if(v > 100) v = 100;
   return(v);
}

void GetCotRetail(int i, int &cot, int &ret) {
   switch(i) {
      case 0: cot = COT_EURUSD; ret = RET_EURUSD; break;
      case 1: cot = COT_GBPUSD; ret = RET_GBPUSD; break;
      case 2: cot = COT_USDJPY; ret = RET_USDJPY; break;
      case 3: cot = COT_XAUUSD; ret = RET_XAUUSD; break;
      case 4: cot = COT_AUDUSD; ret = RET_AUDUSD; break;
      case 5: cot = COT_USDCAD; ret = RET_USDCAD; break;
      case 6: cot = COT_USDCHF; ret = RET_USDCHF; break;
      default: cot = 0; ret = 50;
   }
}

double Randn() {
   double u = MathMax((double)MathRand() / 32767.0, 1e-12);
   double v = (double)MathRand() / 32767.0;
   return(MathSqrt(-2.0 * MathLog(u)) * MathCos(2.0 * M_PI * v));
}

double MonteCarlo(string sym, double price, int combined, int dir, double &tp, double &sl) {
   double atr = iATR(sym, PERIOD_M5, 14, 0);
   if(atr <= 0 || price <= 0) return(-1);

   double vol = (atr / price) * 0.5;
   double str = MathAbs(combined - 50.0) / 50.0;
   double MU  = dir * str * vol * 0.6;
   double SIG = vol * 1.1;
   int    N   = MC_Paths;
   int    STEPS = HorizonSteps();
   double DT  = HorizonDt();

   double finals[];
   ArrayResize(finals, N);
   int favor = 0;

   for(int n = 0; n < N; n++) {
      double p = price;
      for(int t = 0; t < STEPS; t++)
         p = p * MathExp((MU - 0.5*SIG*SIG)*DT + SIG*MathSqrt(DT)*Randn());
      finals[n] = p;
      if((dir > 0 && p > price) || (dir < 0 && p < price)) favor++;
   }
   ArraySort(finals);

   double p5  = finals[(int)(N * 0.05)];
   double p25 = finals[(int)(N * 0.25)];
   double p75 = finals[(int)(N * 0.75)];
   double p95 = finals[(int)(N * 0.95)];

   if(dir > 0) {
      tp = p75;
      sl = p5;
      if(tp <= price || sl >= price) return(-1);
   } else {
      tp = p25;
      sl = p95;
      if(tp >= price || sl <= price) return(-1);
   }

   double minStop = MarketInfo(sym, MODE_STOPLEVEL) * MarketInfo(sym, MODE_POINT);
   if(MathAbs(price - sl) < minStop || MathAbs(tp - price) < minStop) return(-1);

   return((double)favor / N * 100.0);
}

double JsonNumber(string json, string key) {
   string pat = "\"" + key + "\":";
   int idx = StringFind(json, pat);
   if(idx < 0) return(0);
   int p = idx + StringLen(pat);
   while(p < StringLen(json) && StringGetCharacter(json, p) == ' ') p++;
   string num = "";
   for(int i = p; i < StringLen(json); i++) {
      ushort c = StringGetCharacter(json, i);
      if((c >= '0' && c <= '9') || c == '.' || c == '-' || c == '+' || c == 'e' || c == 'E')
         num += ShortToString(c);
      else break;
   }
   if(StringLen(num) == 0) return(0);
   return(StringToDouble(num));
}

string JsonString(string json, string key) {
   string pat = "\"" + key + "\":\"";
   int idx = StringFind(json, pat);
   if(idx < 0) return("");
   int start = idx + StringLen(pat);
   int end   = StringFind(json, "\"", start);
   if(end < 0) return("");
   return(StringSubstr(json, start, end - start));
}

bool JsonBool(string json, string key) {
   string pat = "\"" + key + "\":";
   int idx = StringFind(json, pat);
   if(idx < 0) return(false);
   int start = idx + StringLen(pat);
   while(start < StringLen(json) && StringGetCharacter(json, start) == ' ') start++;
   string tail = StringSubstr(json, start, 5);
   return(StringFind(tail, "true") == 0);
}

int AtlasWebRequest(string url, char &post[], char &result[], string &responseHeaders) {
   string requestHeaders = "";
   if(StringLen(DataApiKey) > 0)
      requestHeaders = "X-API-Key: " + DataApiKey + "\r\n";

   ResetLastError();
   return(WebRequest("GET", url, requestHeaders, ApiTimeoutMs, post, result, responseHeaders));
}

void PrintApiError(string sym, string url, int code, int err) {
   lastApiFailTime = TimeCurrent();
   if(err == 5200) {
      lastApiError = StringFormat("%s err=5200 WebRequest no autorizado", sym);
      PrintFormat("ATLAS API %s -> http=%d err=%d URL invalida/no autorizada: %s. Autoriza exactamente http://127.0.0.1:8000/ en Tools->Options->Expert Advisors.",
                  sym, code, err, url);
   } else if(err == 4060) {
      lastApiError = StringFormat("%s err=4060 WebRequest bloqueado", sym);
      PrintFormat("ATLAS API: WebRequest no autorizado. Agrega la URL base en Tools->Options->Expert Advisors: %s", url);
   } else {
      lastApiError = StringFormat("%s http=%d err=%d", sym, code, err);
      PrintFormat("ATLAS API %s -> http=%d err=%d url=%s", sym, code, err, url);
   }
}

string JoinUrl(string baseUrl, string path, string sym) {
   string url = baseUrl;
   if(StringLen(url) == 0) return("");
   if(StringSubstr(url, StringLen(url) - 1, 1) != "/")
      url = url + "/";
   if(UseFlatApiUrl)
      return(url + "?symbol=" + sym);
   if(StringLen(path) > 0 && StringSubstr(path, 0, 1) == "/")
      path = StringSubstr(path, 1);
   return(url + path + sym);
}

bool FetchContext(string sym, int &scoreAdj, string &risk, bool &blockTrading,
                  string &bias, int &confidence, bool &tradeable, double &expectedRangePips,
                  string &bias5m, string &bias1h, string &bias1d,
                  int &conf5m, int &conf1h, int &conf1d) {
   scoreAdj = 0;
   risk = "";
   blockTrading = false;
   bias = "NEUTRAL";
   bias5m = "NEUTRAL";
   bias1h = "NEUTRAL";
   bias1d = "NEUTRAL";
   confidence = 0;
   conf5m = 0;
   conf1h = 0;
   conf1d = 0;
   tradeable = true;
   expectedRangePips = 0.0;

   string url = JoinUrl(DataApiUrl, DataApiPath, sym);
   char   post[], result[];
   string responseHeaders = "";

   int code = AtlasWebRequest(url, post, result, responseHeaders);
   if(code != 200) {
      int err = GetLastError();
      if(StringLen(BackupDataApiUrl) > 0 && BackupDataApiUrl != DataApiUrl) {
         string backupUrl = JoinUrl(BackupDataApiUrl, DataApiPath, sym);
         ArrayResize(result, 0);
         responseHeaders = "";
         code = AtlasWebRequest(backupUrl, post, result, responseHeaders);
         if(code == 200)
            url = backupUrl;
         else {
            PrintApiError(sym, url, code, err);
            PrintApiError(sym, backupUrl, code, GetLastError());
            return(false);
         }
      } else {
         PrintApiError(sym, url, code, err);
         return(false);
      }
   }

   string body = CharArrayToString(result);
   lastApiOkTime = TimeCurrent();
   lastApiError = "";
   string horizon = NormalizeHorizon();
   StringToLower(horizon);
   scoreAdj = (int)JsonNumber(body, "score_adjust_" + horizon);
   if(scoreAdj == 0 && StringFind(body, "\"score_adjust_" + horizon + "\":") < 0)
      scoreAdj = (int)JsonNumber(body, "score_adjust");

   bias = JsonString(body, "bias_" + horizon);
   if(StringLen(bias) == 0)
      bias = JsonString(body, "bias");

   confidence = (int)JsonNumber(body, "confidence_" + horizon);
   if(confidence == 0 && StringFind(body, "\"confidence_" + horizon + "\":") < 0)
      confidence = (int)JsonNumber(body, "confidence");

   expectedRangePips = JsonNumber(body, "expected_range_" + horizon + "_pips");
   if(expectedRangePips <= 0)
      expectedRangePips = JsonNumber(body, "expected_range_1h_pips");

   risk = JsonString(body, "news_risk");
   blockTrading = JsonBool(body, "block_trading");
   tradeable = JsonBool(body, "tradeable_" + horizon);
   if(StringFind(body, "\"tradeable_" + horizon + "\":") < 0)
      tradeable = JsonBool(body, "tradeable");

   bias5m = JsonString(body, "bias_5m");
   bias1h = JsonString(body, "bias_1h");
   bias1d = JsonString(body, "bias_1d");
   conf5m = (int)JsonNumber(body, "confidence_5m");
   conf1h = (int)JsonNumber(body, "confidence_1h");
   conf1d = (int)JsonNumber(body, "confidence_1d");
   if(StringLen(bias5m) == 0) bias5m = "NEUTRAL";
   if(StringLen(bias1h) == 0) bias1h = "NEUTRAL";
   if(StringLen(bias1d) == 0) bias1d = "NEUTRAL";
   return(true);
}

double CalcLots(string sym, double price, double sl) {
   double riskMoney  = AccountBalance() * RiskPercent / 100.0;
   double slDistance = MathAbs(price - sl);
   if(slDistance <= 0) return(0);

   double tickValue = MarketInfo(sym, MODE_TICKVALUE);
   double tickSize  = MarketInfo(sym, MODE_TICKSIZE);
   if(tickSize <= 0 || tickValue <= 0) return(0);

   double lossPerLot = (slDistance / tickSize) * tickValue;
   if(lossPerLot <= 0) return(0);

   double lots = riskMoney / lossPerLot;
   double minLot = MarketInfo(sym, MODE_MINLOT);
   double maxLot = MarketInfo(sym, MODE_MAXLOT);
   double step   = MarketInfo(sym, MODE_LOTSTEP);
   if(step <= 0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < minLot) return(0);
   if(lots > maxLot) lots = maxLot;
   return(lots);
}
