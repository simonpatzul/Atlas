// Ejemplo minimo para consumir /mt4/context/{symbol} desde MetaTrader 4.
// Recuerda habilitar WebRequest para la URL de tu API:
// Tools -> Options -> Expert Advisors -> Allow WebRequest for listed URL
// Ejemplo: http://127.0.0.1:8000

string ApiKey = "";
string Horizon = "1H";

string ExtractJsonValue(string json, string key)
{
   string needle = "\"" + key + "\":";
   int start = StringFind(json, needle);
   if(start < 0) return "";
   start += StringLen(needle);

   while(start < StringLen(json) && (StringGetCharacter(json, start) == ' ' || StringGetCharacter(json, start) == '\"'))
      start++;

   int end = start;
   while(end < StringLen(json))
   {
      int ch = StringGetCharacter(json, end);
      if(ch == ',' || ch == '}' || ch == '\"')
         break;
      end++;
   }
   return StringSubstr(json, start, end - start);
}

bool FetchAtlasContext(string symbol, string &response)
{
   string url = "http://127.0.0.1:8000/mt4/context/" + symbol;
   string requestHeaders = "Content-Type: application/json\r\n";
   string responseHeaders;
   char post[];
   char result[];
   if(StringLen(ApiKey) > 0)
      requestHeaders = requestHeaders + "X-API-Key: " + ApiKey + "\r\n";

   int timeout = 5000;
   int code = WebRequest("GET", url, requestHeaders, timeout, post, result, responseHeaders);
   if(code == -1)
   {
      Print("WebRequest fallo. Error=", GetLastError());
      return false;
   }
   if(code != 200)
   {
      Print("ATLAS respondio HTTP ", code);
      return false;
   }

   response = CharArrayToString(result);
   return true;
}

void OnStart()
{
   string json;
   if(!FetchAtlasContext("EURUSD", json))
      return;

   string suffix = Horizon;
   StringToLower(suffix);
   string bias = ExtractJsonValue(json, "bias_" + suffix);
   string confidence = ExtractJsonValue(json, "confidence_" + suffix);
   string scoreAdjust = ExtractJsonValue(json, "score_adjust_" + suffix);
   string expectedRange = ExtractJsonValue(json, "expected_range_" + suffix + "_pips");
   string newsRisk = ExtractJsonValue(json, "news_risk");
   string blockTrading = ExtractJsonValue(json, "block_trading");

   Print("ATLAS horizon=", Horizon,
         " bias=", bias,
         " confidence=", confidence,
         " score_adjust=", scoreAdjust,
         " expected_range=", expectedRange,
         " news_risk=", newsRisk,
         " block_trading=", blockTrading);
}
