#property strict
#property copyright "ATLAS"
#property version   "1.00"
#property description "RUTA v5 M1 Adaptive Learner + contexto macro/noticias ATLAS"

// ======================================================
// RUTA v5 M1 ADAPTIVE LEARNER
// EURUSD M5 Mean Reversion + estado M30
// + aprendizaje microestructural en M1
// + SL/TP/Trailing recalculado en cada barra M1
// + filtro macro, noticias, calendario, COT y sentimiento via ATLAS API
// ======================================================

// ---------------------------
// Inputs generales
// ---------------------------
input string InpSymbol               = "";
input int    InpMagic                = 26041801;
input bool   InpOneTradePerSymbol    = true;
input bool   InpAllowOnReal          = false;

// ---------------------------
// Timeframes
// ---------------------------
input int    InpExecTF               = PERIOD_M5;
input int    InpStateTF              = PERIOD_M30;
input int    InpManageTF             = PERIOD_M1;
input int    InpLearnTF              = PERIOD_M1;

// ---------------------------
// Filtro horario
// ---------------------------
input bool   InpUseSessionFilter     = true;
input int    InpSessionStartHour     = 6;
input int    InpSessionEndHour       = 22;

// ---------------------------
// Costos / ejecucion
// ---------------------------
input double InpMaxSpreadPips        = 0.20;
input double InpMaxSlippagePips      = 0.30;

// ---------------------------
// Riesgo
// ---------------------------
input bool   InpUseRiskPercent       = true;
input double InpRiskPercent          = 0.50;
input double InpFixedLots            = 0.01;

// ---------------------------
// Nucleo estadistico M5/M30
// ---------------------------
input int    InpZLookback            = 23;
input int    InpCohPeriod            = 22;
input int    InpUncShort             = 10;
input int    InpUncLong              = 50;

// ---------------------------
// Entrada base M5/M30
// ---------------------------
input double InpZEntry               = 1.9;
input double InpMaxCohExec           = 0.4;
input double InpMaxUncExec           = 1.3;
input double InpMaxCohState          = 0.4;
input double InpMaxUncState          = 1.5;

// ---------------------------
// Salida base
// ---------------------------
input double InpZExit                = 0.0;
input int    InpMaxHoldBars          = 27;

// ---------------------------
// Aprendizaje / anticipacion M1
// ---------------------------
input bool   InpUseM1Learner         = true;
input int    InpM1ZLookback          = 18;
input int    InpM1UncShort           = 8;
input int    InpM1UncLong            = 34;
input int    InpM1FastEMA            = 4;
input int    InpM1SlowEMA            = 11;
input double InpM1EntryScoreMin      = 0.20;
input double InpM1BlockScore         = -0.25;
input int    InpLearnerMinTrades     = 6;
input double InpLearnerWeight        = 0.60;
input double InpHeuristicWeight      = 1.00;
input bool   InpRequireTurnOnM1      = true;

// ---------------------------
// Proteccion inteligente
// ---------------------------
input bool   InpUseSmartProtection   = true;
input int    InpSwingLookback        = 6;
input int    InpTrailSwingLookback   = 4;
input int    InpATRPeriod            = 17;
input int    InpM1ATRPeriod          = 14;
input double InpInitialSL_ATR        = 1.35;
input double InpMinSL_ATR            = 0.85;
input double InpMaxSL_ATR            = 2.10;
input double InpEmergencySL_ATR      = 2.80;
input double InpSwingBufferATR       = 0.15;
input double InpMinTP_RR             = 1.35;
input double InpMaxTP_RR             = 2.60;
input double InpBreakEven_R          = 0.75;
input double InpBreakEvenLock_R      = 0.10;
input double InpTrailStart_R         = 0.90;
input double InpTrailATR_Base        = 1.00;
input double InpTrailATR_Min         = 0.55;
input double InpTrailStep_R          = 0.12;

// ---------------------------
// Contexto ATLAS macro/noticias
// ---------------------------
input bool   InpUseAtlasContext      = true;
input bool   InpRequireAtlasForEntry = true;
input bool   InpCloseOnAtlasConflict = true;
input bool   InpRequireTripleAlign   = false;
input int    InpMinAtlasConfidence   = 38;
input int    InpMinAtlasScoreAbs     = 3;
input string InpAtlasApiUrl          = "https://atlas-delta-nine.vercel.app/api/";
input string InpAtlasApiKey          = "";
input int    InpAtlasTimeoutMs       = 4000;
input int    InpAtlasRefreshSec      = 60;
input bool   InpUseFlatApiUrl        = true;

struct AtlasContext {
   bool ok;
   bool blockTrading;
   bool tradeable5m;
   bool tradeable1h;
   bool tradeable1d;
   string newsRisk;
   string bias5m;
   string bias1h;
   string bias1d;
   int conf5m;
   int conf1h;
   int conf1d;
   int score5m;
   int score1h;
   int score1d;
   int newsBoost;
   double macroBias;
   double cotBias;
   double sentimentBias;
   double expectedRange5m;
   double nextEventMinutes;
};

datetime g_lastM1Bar = 0;
datetime g_lastApiFetch = 0;
datetime g_lastApiOk = 0;
datetime g_lastApiFail = 0;
datetime g_lastLearnScan = 0;
string   g_lastApiError = "";
AtlasContext g_ctx;
double   gMaxSpreadPips = 0.0;
double   gZEntry = 0.0;
double   gInitialSL_ATR = 0.0;
double   gEmergencySL_ATR = 0.0;

string TradeSymbol() {
   if(StringLen(InpSymbol) > 0) return(InpSymbol);
   return(Symbol());
}

string BaseSymbol(string sym) {
   string s = sym;
   StringToUpper(s);
   string out = "";
   for(int i = 0; i < StringLen(s); i++) {
      ushort c = StringGetCharacter(s, i);
      if((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))
         out += ShortToString(c);
   }
   if(StringFind(out, "EURUSD") == 0) return("EURUSD");
   if(StringFind(out, "GBPUSD") == 0) return("GBPUSD");
   if(StringFind(out, "USDJPY") == 0) return("USDJPY");
   if(StringFind(out, "XAUUSD") == 0) return("XAUUSD");
   if(StringFind(out, "AUDUSD") == 0) return("AUDUSD");
   if(StringFind(out, "USDCAD") == 0) return("USDCAD");
   if(StringFind(out, "USDCHF") == 0) return("USDCHF");
   return(out);
}

double PipSize(string sym) {
   double point = MarketInfo(sym, MODE_POINT);
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   if(digits == 3 || digits == 5) return(point * 10.0);
   return(point);
}

double SpreadPips(string sym) {
   double pip = PipSize(sym);
   if(pip <= 0) return(999.0);
   return((MarketInfo(sym, MODE_ASK) - MarketInfo(sym, MODE_BID)) / pip);
}

int SlippagePoints(string sym) {
   double points = InpMaxSlippagePips * PipSize(sym) / MarketInfo(sym, MODE_POINT);
   return((int)MathMax(1, MathRound(points)));
}

bool InSession() {
   if(!InpUseSessionFilter) return(true);
   int h = TimeHour(TimeCurrent());
   if(InpSessionStartHour == InpSessionEndHour) return(true);
   if(InpSessionStartHour < InpSessionEndHour)
      return(h >= InpSessionStartHour && h < InpSessionEndHour);
   return(h >= InpSessionStartHour || h < InpSessionEndHour);
}

bool NewBar(int tf, datetime &lastBar) {
   datetime t = iTime(TradeSymbol(), tf, 0);
   if(t <= 0 || t == lastBar) return(false);
   lastBar = t;
   return(true);
}

double MeanClose(string sym, int tf, int period, int shift) {
   double sum = 0.0;
   for(int i = shift; i < shift + period; i++)
      sum += iClose(sym, tf, i);
   return(sum / period);
}

double StdClose(string sym, int tf, int period, int shift, double mean) {
   double sum = 0.0;
   for(int i = shift; i < shift + period; i++) {
      double d = iClose(sym, tf, i) - mean;
      sum += d * d;
   }
   return(MathSqrt(sum / MathMax(1, period - 1)));
}

double ZScore(string sym, int tf, int period, int shift) {
   if(iBars(sym, tf) < period + shift + 2) return(0.0);
   double mean = MeanClose(sym, tf, period, shift);
   double sd = StdClose(sym, tf, period, shift, mean);
   if(sd <= 0) return(0.0);
   return((iClose(sym, tf, shift) - mean) / sd);
}

double Coherence(string sym, int tf, int period) {
   if(iBars(sym, tf) < period + 3) return(1.0);
   double first = iClose(sym, tf, period);
   double last = iClose(sym, tf, 1);
   double path = 0.0;
   for(int i = 1; i <= period; i++)
      path += MathAbs(iClose(sym, tf, i) - iClose(sym, tf, i + 1));
   if(path <= 0) return(1.0);
   return(MathAbs(last - first) / path);
}

double Uncertainty(string sym, int tf, int shortPeriod, int longPeriod) {
   double aS = iATR(sym, tf, shortPeriod, 1);
   double aL = iATR(sym, tf, longPeriod, 1);
   if(aS <= 0 || aL <= 0) return(9.0);
   return(aS / aL);
}

bool M1Turn(string sym, int dir) {
   double fast0 = iMA(sym, InpLearnTF, InpM1FastEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double fast1 = iMA(sym, InpLearnTF, InpM1FastEMA, 0, MODE_EMA, PRICE_CLOSE, 2);
   double slow0 = iMA(sym, InpLearnTF, InpM1SlowEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slow1 = iMA(sym, InpLearnTF, InpM1SlowEMA, 0, MODE_EMA, PRICE_CLOSE, 2);
   if(dir > 0) return(fast0 > fast1 && fast0 >= slow0 && fast1 <= slow1);
   return(fast0 < fast1 && fast0 <= slow0 && fast1 >= slow1);
}

double GlobalGetDef(string key, double defValue) {
   if(!GlobalVariableCheck(key)) return(defValue);
   return(GlobalVariableGet(key));
}

void GlobalSetVal(string key, double value) {
   GlobalVariableSet(key, value);
}

string LearnPrefix(string sym) {
   return("RUTA5." + BaseSymbol(sym) + "." + IntegerToString(InpMagic) + ".");
}

double LearnerEdge(string sym, int dir) {
   string p = LearnPrefix(sym) + (dir > 0 ? "L" : "S");
   double wins = GlobalGetDef(p + ".wins", 0);
   double losses = GlobalGetDef(p + ".losses", 0);
   double avgWin = GlobalGetDef(p + ".avgWin", 0);
   double avgLoss = GlobalGetDef(p + ".avgLoss", 0);
   double trades = wins + losses;
   if(trades < InpLearnerMinTrades || avgLoss <= 0) return(0.0);
   double winRate = wins / trades;
   double payoff = avgWin / avgLoss;
   return((winRate * payoff) - (1.0 - winRate));
}

double M1Score(string sym, int dir) {
   if(!InpUseM1Learner) return(0.0);
   double z = ZScore(sym, InpLearnTF, InpM1ZLookback, 1);
   double unc = Uncertainty(sym, InpLearnTF, InpM1UncShort, InpM1UncLong);
   double fast = iMA(sym, InpLearnTF, InpM1FastEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slow = iMA(sym, InpLearnTF, InpM1SlowEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slope = (fast - slow) / MathMax(PipSize(sym), 1e-8);
   if(dir < 0) slope = -slope;

   double heuristic = 0.0;
   if(dir > 0 && z < 0) heuristic += MathMin(1.0, MathAbs(z) / InpM1ZLookback);
   if(dir < 0 && z > 0) heuristic += MathMin(1.0, MathAbs(z) / InpM1ZLookback);
   heuristic += MathMax(-0.4, MathMin(0.4, slope / 4.0));
   if(unc > 1.0) heuristic -= MathMin(0.4, (unc - 1.0) * 0.7);
   if(InpRequireTurnOnM1 && !M1Turn(sym, dir)) heuristic -= 0.45;

   double learned = LearnerEdge(sym, dir);
   return(heuristic * InpHeuristicWeight + learned * InpLearnerWeight);
}

void UpdateLearnerFromHistory(string sym) {
   int total = OrdersHistoryTotal();
   for(int i = total - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderMagicNumber() != InpMagic || OrderSymbol() != sym) continue;
      if(OrderCloseTime() <= g_lastLearnScan) break;

      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      int dir = (type == OP_BUY) ? 1 : -1;
      string p = LearnPrefix(sym) + (dir > 0 ? "L" : "S");
      double profit = OrderProfit() + OrderSwap() + OrderCommission();
      double alpha = 0.20;
      if(profit > 0) {
         double wins = GlobalGetDef(p + ".wins", 0) + 1;
         double avgWin = GlobalGetDef(p + ".avgWin", 0);
         avgWin = (avgWin <= 0) ? profit : avgWin * (1.0 - alpha) + profit * alpha;
         GlobalSetVal(p + ".wins", wins);
         GlobalSetVal(p + ".avgWin", avgWin);
      } else if(profit < 0) {
         double losses = GlobalGetDef(p + ".losses", 0) + 1;
         double avgLoss = GlobalGetDef(p + ".avgLoss", 0);
         double loss = MathAbs(profit);
         avgLoss = (avgLoss <= 0) ? loss : avgLoss * (1.0 - alpha) + loss * alpha;
         GlobalSetVal(p + ".losses", losses);
         GlobalSetVal(p + ".avgLoss", avgLoss);
      }
   }
   g_lastLearnScan = TimeCurrent();
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
   int end = StringFind(json, "\"", start);
   if(end < 0) return("");
   return(StringSubstr(json, start, end - start));
}

bool JsonBool(string json, string key) {
   string pat = "\"" + key + "\":";
   int idx = StringFind(json, pat);
   if(idx < 0) return(false);
   int start = idx + StringLen(pat);
   while(start < StringLen(json) && StringGetCharacter(json, start) == ' ') start++;
   return(StringFind(StringSubstr(json, start, 5), "true") == 0);
}

string JoinAtlasUrl(string sym) {
   string url = InpAtlasApiUrl;
   if(StringLen(url) == 0) return("");
   if(StringSubstr(url, StringLen(url) - 1, 1) != "/") url += "/";
   if(InpUseFlatApiUrl) return(url + "?symbol=" + BaseSymbol(sym));
   return(url + "mt4/context/" + BaseSymbol(sym));
}

bool FetchAtlas(string sym, AtlasContext &ctx) {
   ctx.ok = false;
   ctx.blockTrading = false;
   ctx.tradeable5m = false;
   ctx.tradeable1h = false;
   ctx.tradeable1d = false;
   ctx.newsRisk = "";
   ctx.bias5m = "NEUTRAL";
   ctx.bias1h = "NEUTRAL";
   ctx.bias1d = "NEUTRAL";
   ctx.conf5m = 0;
   ctx.conf1h = 0;
   ctx.conf1d = 0;
   ctx.score5m = 0;
   ctx.score1h = 0;
   ctx.score1d = 0;
   ctx.newsBoost = 0;
   ctx.macroBias = 0;
   ctx.cotBias = 0;
   ctx.sentimentBias = 0;
   ctx.expectedRange5m = 0;
   ctx.nextEventMinutes = 0;

   string url = JoinAtlasUrl(sym);
   char post[], result[];
   string headers = "";
   if(StringLen(InpAtlasApiKey) > 0) headers = "X-API-Key: " + InpAtlasApiKey + "\r\n";
   string responseHeaders = "";
   ResetLastError();
   int code = WebRequest("GET", url, headers, InpAtlasTimeoutMs, post, result, responseHeaders);
   if(code != 200) {
      int err = GetLastError();
      g_lastApiFail = TimeCurrent();
      g_lastApiError = StringFormat("http=%d err=%d", code, err);
      PrintFormat("RUTA v5 ATLAS fallo %s url=%s http=%d err=%d", sym, url, code, err);
      return(false);
   }

   string body = CharArrayToString(result);
   ctx.blockTrading = JsonBool(body, "block_trading");
   ctx.tradeable5m = JsonBool(body, "tradeable_5m");
   ctx.tradeable1h = JsonBool(body, "tradeable_1h");
   ctx.tradeable1d = JsonBool(body, "tradeable_1d");
   ctx.newsRisk = JsonString(body, "news_risk");
   ctx.bias5m = JsonString(body, "bias_5m");
   ctx.bias1h = JsonString(body, "bias_1h");
   ctx.bias1d = JsonString(body, "bias_1d");
   ctx.conf5m = (int)JsonNumber(body, "confidence_5m");
   ctx.conf1h = (int)JsonNumber(body, "confidence_1h");
   ctx.conf1d = (int)JsonNumber(body, "confidence_1d");
   ctx.score5m = (int)JsonNumber(body, "score_adjust_5m");
   ctx.score1h = (int)JsonNumber(body, "score_adjust_1h");
   ctx.score1d = (int)JsonNumber(body, "score_adjust_1d");
   ctx.newsBoost = (int)JsonNumber(body, "news_surprise_boost");
   ctx.macroBias = JsonNumber(body, "macro_bias");
   ctx.cotBias = JsonNumber(body, "cot_bias");
   ctx.sentimentBias = JsonNumber(body, "sentiment_bias");
   ctx.expectedRange5m = JsonNumber(body, "expected_range_5m_pips");
   ctx.nextEventMinutes = JsonNumber(body, "next_event_minutes");
   if(StringLen(ctx.bias5m) == 0) ctx.bias5m = "NEUTRAL";
   if(StringLen(ctx.bias1h) == 0) ctx.bias1h = "NEUTRAL";
   if(StringLen(ctx.bias1d) == 0) ctx.bias1d = "NEUTRAL";
   ctx.ok = true;
   g_lastApiOk = TimeCurrent();
   g_lastApiError = "";
   return(true);
}

bool EnsureAtlas(string sym) {
   if(!InpUseAtlasContext) return(true);
   if(TimeCurrent() - g_lastApiFetch < InpAtlasRefreshSec && g_ctx.ok) return(true);
   g_lastApiFetch = TimeCurrent();
   return(FetchAtlas(sym, g_ctx));
}

bool TripleAligned(AtlasContext &ctx, int dir) {
   string want = (dir > 0) ? "UP" : "DOWN";
   return(ctx.bias5m == want && ctx.bias1h == want && ctx.bias1d == want);
}

double AtlasDirectionalScore(AtlasContext &ctx, int dir) {
   if(!ctx.ok) return(0.0);
   string want = (dir > 0) ? "UP" : "DOWN";
   string opp = (dir > 0) ? "DOWN" : "UP";
   double s = 0.0;
   if(ctx.bias5m == want) s += 0.30;
   if(ctx.bias1h == want) s += 0.45;
   if(ctx.bias1d == want) s += 0.25;
   if(ctx.bias5m == opp) s -= 0.45;
   if(ctx.bias1h == opp) s -= 0.60;
   if(ctx.bias1d == opp) s -= 0.35;
   s += dir * (ctx.score5m * 0.035 + ctx.score1h * 0.045 + ctx.score1d * 0.020);
   s += dir * (ctx.macroBias * 0.35 + ctx.cotBias * 0.20 + ctx.sentimentBias * 0.20);
   s += dir * ctx.newsBoost * 0.08;
   if(ctx.newsRisk == "MEDIUM") s -= 0.20;
   if(ctx.newsRisk == "HIGH") s -= 0.80;
   return(s);
}

bool AtlasAllowsEntry(AtlasContext &ctx, int dir, string &reason) {
   reason = "";
   if(!InpUseAtlasContext) return(true);
   if(!ctx.ok) {
      reason = "ATLAS_OFF";
      return(!InpRequireAtlasForEntry);
   }
   if(ctx.blockTrading || ctx.newsRisk == "HIGH") {
      reason = "NEWS_BLOCK";
      return(false);
   }
   if(!ctx.tradeable5m && !ctx.tradeable1h) {
      reason = "NO_TRADEABLE";
      return(false);
   }
   if(ctx.conf5m < InpMinAtlasConfidence && ctx.conf1h < InpMinAtlasConfidence) {
      reason = "LOW_CONF";
      return(false);
   }
   if(InpRequireTripleAlign && !TripleAligned(ctx, dir)) {
      reason = "NO_TRIPLE";
      return(false);
   }
   double directional = AtlasDirectionalScore(ctx, dir);
   if(MathAbs(ctx.score5m) < InpMinAtlasScoreAbs && MathAbs(ctx.score1h) < InpMinAtlasScoreAbs && directional < 0.25) {
      reason = "LOW_ATLAS_SCORE";
      return(false);
   }
   if(directional < -0.15) {
      reason = "ATLAS_CONFLICT";
      return(false);
   }
   return(true);
}

bool BaseSignal(string sym, int dir, double &baseScore) {
   double zExec = ZScore(sym, InpExecTF, InpZLookback, 1);
   double zState = ZScore(sym, InpStateTF, InpZLookback, 1);
   double cohExec = Coherence(sym, InpExecTF, InpCohPeriod);
   double cohState = Coherence(sym, InpStateTF, InpCohPeriod);
   double uncExec = Uncertainty(sym, InpExecTF, InpUncShort, InpUncLong);
   double uncState = Uncertainty(sym, InpStateTF, InpUncShort, InpUncLong);

   bool zOk = (dir > 0) ? (zExec <= -gZEntry) : (zExec >= gZEntry);
   bool stateOk = (dir > 0) ? (zState <= 0.75) : (zState >= -0.75);
   bool regimeOk = (cohExec <= InpMaxCohExec && cohState <= InpMaxCohState &&
                    uncExec <= InpMaxUncExec && uncState <= InpMaxUncState);

   baseScore = 0.0;
   if(zOk) baseScore += MathMin(1.2, MathAbs(zExec) / gZEntry);
   if(stateOk) baseScore += 0.35;
   if(regimeOk) baseScore += 0.35;
   baseScore -= MathMax(0.0, cohExec - InpMaxCohExec);
   baseScore -= MathMax(0.0, uncExec - InpMaxUncExec) * 0.4;
   return(zOk && stateOk && regimeOk);
}

int FindMyOrder(string sym) {
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() == InpMagic && OrderSymbol() == sym)
         return(OrderTicket());
   }
   return(-1);
}

double StopLevelDistance(string sym) {
   return(MarketInfo(sym, MODE_STOPLEVEL) * MarketInfo(sym, MODE_POINT));
}

double SwingLow(string sym, int tf, int lookback) {
   double v = iLow(sym, tf, 1);
   for(int i = 2; i <= lookback; i++) v = MathMin(v, iLow(sym, tf, i));
   return(v);
}

double SwingHigh(string sym, int tf, int lookback) {
   double v = iHigh(sym, tf, 1);
   for(int i = 2; i <= lookback; i++) v = MathMax(v, iHigh(sym, tf, i));
   return(v);
}

void BuildProtection(string sym, int dir, double entry, double edgeScore, double &sl, double &tp) {
   double atr = iATR(sym, InpExecTF, InpATRPeriod, 1);
   double pip = PipSize(sym);
   if(atr <= 0) atr = 10.0 * pip;
   double slAtr = gInitialSL_ATR;
   if(edgeScore > 1.6) slAtr *= 0.92;
   if(g_ctx.ok && g_ctx.newsRisk == "MEDIUM") slAtr *= 1.15;
   slAtr = MathMax(InpMinSL_ATR, MathMin(InpMaxSL_ATR, slAtr));

   double dist = slAtr * atr;
   double emergency = gEmergencySL_ATR * atr;
   dist = MathMin(dist, emergency);

   double swingBuffer = InpSwingBufferATR * atr;
   if(dir > 0) {
      double swing = SwingLow(sym, InpExecTF, InpSwingLookback) - swingBuffer;
      sl = MathMin(entry - dist, swing);
      double risk = entry - sl;
      risk = MathMax(risk, StopLevelDistance(sym));
      double rr = MathMin(InpMaxTP_RR, MathMax(InpMinTP_RR, InpMinTP_RR + MathMax(0, edgeScore - 1.0) * 0.35));
      tp = entry + risk * rr;
   } else {
      double swing = SwingHigh(sym, InpExecTF, InpSwingLookback) + swingBuffer;
      sl = MathMax(entry + dist, swing);
      double risk = sl - entry;
      risk = MathMax(risk, StopLevelDistance(sym));
      double rr = MathMin(InpMaxTP_RR, MathMax(InpMinTP_RR, InpMinTP_RR + MathMax(0, edgeScore - 1.0) * 0.35));
      tp = entry - risk * rr;
   }
}

double CalcLots(string sym, double entry, double sl) {
   if(!InpUseRiskPercent) return(InpFixedLots);
   double riskMoney = AccountBalance() * InpRiskPercent / 100.0;
   double slDistance = MathAbs(entry - sl);
   if(riskMoney <= 0 || slDistance <= 0) return(0);
   double tickValue = MarketInfo(sym, MODE_TICKVALUE);
   double tickSize = MarketInfo(sym, MODE_TICKSIZE);
   if(tickValue <= 0 || tickSize <= 0) return(0);
   double lossPerLot = (slDistance / tickSize) * tickValue;
   if(lossPerLot <= 0) return(0);
   double lots = riskMoney / lossPerLot;
   double minLot = MarketInfo(sym, MODE_MINLOT);
   double maxLot = MarketInfo(sym, MODE_MAXLOT);
   double step = MarketInfo(sym, MODE_LOTSTEP);
   if(step <= 0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < minLot) return(0);
   if(lots > maxLot) lots = maxLot;
   return(lots);
}

bool ModifyIfImproves(int ticket, double sl, double tp, color col) {
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return(false);
   int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);
   if(MathAbs(OrderStopLoss() - sl) < MarketInfo(OrderSymbol(), MODE_POINT) &&
      MathAbs(OrderTakeProfit() - tp) < MarketInfo(OrderSymbol(), MODE_POINT))
      return(true);
   ResetLastError();
   bool ok = OrderModify(ticket, OrderOpenPrice(), sl, tp, 0, col);
   if(!ok) PrintFormat("RUTA v5 OrderModify fallo ticket=%d err=%d", ticket, GetLastError());
   return(ok);
}

void ManageProtection(int ticket) {
   if(!InpUseSmartProtection) return;
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
   string sym = OrderSymbol();
   int type = OrderType();
   if(type != OP_BUY && type != OP_SELL) return;

   double atr = iATR(sym, InpManageTF, InpM1ATRPeriod, 1);
   if(atr <= 0) return;
   double entry = OrderOpenPrice();
   double current = (type == OP_BUY) ? MarketInfo(sym, MODE_BID) : MarketInfo(sym, MODE_ASK);
   double risk = MathAbs(entry - OrderStopLoss());
   if(risk <= 0) return;
   double rNow = (type == OP_BUY) ? (current - entry) / risk : (entry - current) / risk;
   double newSl = OrderStopLoss();
   double tp = OrderTakeProfit();
   double minStop = StopLevelDistance(sym);

   if(rNow >= InpBreakEven_R) {
      double lock = risk * InpBreakEvenLock_R;
      if(type == OP_BUY) newSl = MathMax(newSl, entry + lock);
      else newSl = MathMin(newSl <= 0 ? entry - lock : newSl, entry - lock);
   }

   if(rNow >= InpTrailStart_R) {
      double trailAtr = MathMax(InpTrailATR_Min, InpTrailATR_Base) * atr;
      if(type == OP_BUY) {
         double swing = SwingLow(sym, InpManageTF, InpTrailSwingLookback) - InpSwingBufferATR * atr;
         double trail = MathMax(swing, current - trailAtr);
         if(current - trail < minStop) trail = current - minStop;
         if(trail > newSl + risk * InpTrailStep_R) newSl = trail;
      } else {
         double swing = SwingHigh(sym, InpManageTF, InpTrailSwingLookback) + InpSwingBufferATR * atr;
         double trail = MathMin(swing, current + trailAtr);
         if(trail - current < minStop) trail = current + minStop;
         if(newSl <= 0 || trail < newSl - risk * InpTrailStep_R) newSl = trail;
      }
   }

   ModifyIfImproves(ticket, newSl, tp, clrDodgerBlue);
}

void CloseOrder(int ticket, string reason) {
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;
   string sym = OrderSymbol();
   double price = (OrderType() == OP_BUY) ? MarketInfo(sym, MODE_BID) : MarketInfo(sym, MODE_ASK);
   ResetLastError();
   bool ok = OrderClose(ticket, OrderLots(), price, SlippagePoints(sym), clrYellow);
   PrintFormat("RUTA v5 cierre %s ticket=%d reason=%s ok=%s err=%d",
               sym, ticket, reason, ok ? "si" : "no", ok ? 0 : GetLastError());
}

bool ShouldCloseBySignal(string sym, int ticket) {
   if(!OrderSelect(ticket, SELECT_BY_TICKET)) return(false);
   int type = OrderType();
   int dir = (type == OP_BUY) ? 1 : -1;
   double z = ZScore(sym, InpExecTF, InpZLookback, 1);
   if((dir > 0 && z >= InpZExit) || (dir < 0 && z <= -InpZExit))
      return(true);

   int barsHeld = iBarShift(sym, InpExecTF, OrderOpenTime(), true);
   if(barsHeld < 0) barsHeld = (int)((TimeCurrent() - OrderOpenTime()) / (PeriodSeconds(InpExecTF)));
   if(barsHeld >= InpMaxHoldBars) return(true);

   if(InpUseAtlasContext && InpCloseOnAtlasConflict && g_ctx.ok) {
      if(g_ctx.blockTrading || g_ctx.newsRisk == "HIGH") return(true);
      double atlas = AtlasDirectionalScore(g_ctx, dir);
      if(atlas < -0.35) return(true);
      if(InpRequireTripleAlign && !TripleAligned(g_ctx, dir)) return(true);
   }
   return(false);
}

void TryOpen(string sym) {
   if(!InSession()) return;
   if(SpreadPips(sym) > gMaxSpreadPips) {
      PrintFormat("RUTA v5 spread alto %s %.2f pips", sym, SpreadPips(sym));
      return;
   }
   if(InpOneTradePerSymbol && FindMyOrder(sym) >= 0) return;
   if(InpUseAtlasContext && !EnsureAtlas(sym) && InpRequireAtlasForEntry) return;

   for(int dir = 1; dir >= -1; dir -= 2) {
      double baseScore = 0.0;
      if(!BaseSignal(sym, dir, baseScore)) continue;
      double m1 = M1Score(sym, dir);
      if(m1 < InpM1BlockScore) continue;
      if(InpUseM1Learner && m1 < InpM1EntryScoreMin) continue;

      string reason = "";
      if(!AtlasAllowsEntry(g_ctx, dir, reason)) {
         PrintFormat("RUTA v5 bloqueo ATLAS %s dir=%d reason=%s", sym, dir, reason);
         continue;
      }

      double atlas = AtlasDirectionalScore(g_ctx, dir);
      double edge = baseScore + m1 + atlas;
      if(edge < 1.35) continue;

      double entry = (dir > 0) ? MarketInfo(sym, MODE_ASK) : MarketInfo(sym, MODE_BID);
      double sl = 0, tp = 0;
      BuildProtection(sym, dir, entry, edge, sl, tp);
      int digits = (int)MarketInfo(sym, MODE_DIGITS);
      sl = NormalizeDouble(sl, digits);
      tp = NormalizeDouble(tp, digits);
      double lots = CalcLots(sym, entry, sl);
      if(lots <= 0) {
         PrintFormat("RUTA v5 lotes=0 %s", sym);
         return;
      }

      int type = (dir > 0) ? OP_BUY : OP_SELL;
      string comment = StringFormat("RUTA5 edge=%.2f b=%.2f m1=%.2f a=%.2f %s/%s/%s",
                                    edge, baseScore, m1, atlas, g_ctx.bias5m, g_ctx.bias1h, g_ctx.bias1d);
      ResetLastError();
      int ticket = OrderSend(sym, type, lots, NormalizeDouble(entry, digits), SlippagePoints(sym),
                             sl, tp, comment, InpMagic, 0, dir > 0 ? clrLime : clrTomato);
      if(ticket < 0) {
         PrintFormat("RUTA v5 OrderSend fallo %s dir=%d err=%d lots=%.2f entry=%.5f sl=%.5f tp=%.5f",
                     sym, dir, GetLastError(), lots, entry, sl, tp);
      } else {
         PrintFormat("RUTA v5 abre %s %s lots=%.2f entry=%.5f sl=%.5f tp=%.5f edge=%.2f atlas=%.2f",
                     dir > 0 ? "BUY" : "SELL", sym, lots, entry, sl, tp, edge, atlas);
      }
      return;
   }
}

void ApplyPairPreset(string sym) {
   string b = BaseSymbol(sym);
   if(b == "EURUSD") {
      // Parametros base: mean reversion M5 con contexto EUR/USD.
      return;
   }
   if(b == "GBPUSD") {
      gMaxSpreadPips = MathMax(gMaxSpreadPips, 0.30);
   } else if(b == "USDJPY") {
      gZEntry = MathMax(gZEntry, 2.0);
      gMaxSpreadPips = MathMax(gMaxSpreadPips, 0.25);
   } else if(b == "XAUUSD") {
      gZEntry = MathMax(gZEntry, 2.2);
      gMaxSpreadPips = MathMax(gMaxSpreadPips, 3.0);
      gInitialSL_ATR = MathMax(gInitialSL_ATR, 1.65);
      gEmergencySL_ATR = MathMax(gEmergencySL_ATR, 3.20);
   } else if(b == "AUDUSD" || b == "USDCAD" || b == "USDCHF") {
      gZEntry = MathMax(gZEntry, 2.0);
      gMaxSpreadPips = MathMax(gMaxSpreadPips, 0.35);
   }
}

void UpdatePanel(string sym) {
   string api = g_ctx.ok ? "OK" : "OFF";
   Comment(
      "RUTA v5 ATLAS Adaptive Learner\n",
      "Simbolo: ", sym, " | API: ", api, " | error: ", g_lastApiError, "\n",
      "Bias: 5M=", g_ctx.bias5m, " 1H=", g_ctx.bias1h, " 1D=", g_ctx.bias1d,
      " | conf=", g_ctx.conf5m, "/", g_ctx.conf1h, "/", g_ctx.conf1d, "\n",
      "News: ", g_ctx.newsRisk, " | block=", g_ctx.blockTrading ? "si" : "no",
      " | score=", g_ctx.score5m, "/", g_ctx.score1h, "/", g_ctx.score1d, "\n",
      "Macro=", DoubleToString(g_ctx.macroBias, 3),
      " COT=", DoubleToString(g_ctx.cotBias, 3),
      " Sent=", DoubleToString(g_ctx.sentimentBias, 3), "\n",
      "M1 learner L/S=", DoubleToString(LearnerEdge(sym, 1), 2), "/",
      DoubleToString(LearnerEdge(sym, -1), 2)
   );
}

int OnInit() {
   string sym = TradeSymbol();
   if(!IsDemo() && !InpAllowOnReal) {
      Alert("RUTA v5: cuenta REAL detectada e InpAllowOnReal=false. EA detenido.");
      return(INIT_FAILED);
   }
   gMaxSpreadPips = InpMaxSpreadPips;
   gZEntry = InpZEntry;
   gInitialSL_ATR = InpInitialSL_ATR;
   gEmergencySL_ATR = InpEmergencySL_ATR;
   ApplyPairPreset(sym);
   MathSrand((int)TimeLocal());
   PrintFormat("RUTA v5 iniciado sym=%s base=%s risk=%.2f%% api=%s",
               sym, BaseSymbol(sym), InpRiskPercent, InpUseAtlasContext ? "si" : "no");
   EnsureAtlas(sym);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {
   Comment("");
   PrintFormat("RUTA v5 detenido reason=%d", reason);
}

void OnTick() {
   string sym = TradeSymbol();
   if(MarketInfo(sym, MODE_BID) <= 0) return;
   EnsureAtlas(sym);
   UpdateLearnerFromHistory(sym);

   int ticket = FindMyOrder(sym);
   if(ticket >= 0) {
      if(NewBar(InpManageTF, g_lastM1Bar))
         ManageProtection(ticket);
      if(ShouldCloseBySignal(sym, ticket))
         CloseOrder(ticket, "SIGNAL");
   } else {
      if(NewBar(InpManageTF, g_lastM1Bar))
         TryOpen(sym);
   }
   UpdatePanel(sym);
}
