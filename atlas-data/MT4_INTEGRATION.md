# ATLAS MT4 Integration

## Endpoint principal

- `GET /mt4/context/{symbol}`
- Ejemplo: `http://127.0.0.1:8000/mt4/context/EURUSD`

## Respuesta

```json
{
  "symbol": "EURUSD",
  "pair": "EUR/USD",
  "ts_utc": "2026-04-22T15:30:00+00:00",
  "session": {
    "code": "LONDON_NY",
    "label": "Cruce Londres-Nueva York",
    "is_london": true,
    "is_ny": true,
    "is_overlap": true,
    "is_fix_window": false
  },
  "event_block": {
    "active": true,
    "reason": "high_impact_18m",
    "blocked_until_utc": "2026-04-22T15:48:00+00:00",
    "minutes_to_unblock": 12.0
  },
  "bias_5m": "NEUTRAL",
  "bias_1h": "UP",
  "bias_1d": "UP",
  "confidence_5m": 39,
  "confidence_1h": 72,
  "confidence_1d": 81,
  "score_adjust_5m": -3,
  "score_adjust_1h": 11,
  "score_adjust_1d": 16,
  "bias": "UP",
  "confidence": 72,
  "expected_range_5m_pips": 2.5,
  "expected_range_1h_pips": 12.4,
  "expected_range_1d_pips": 74.4,
  "invalidation_hint": "below_prev_hour_low",
  "tradeable_5m": false,
  "tradeable_1h": false,
  "tradeable_1d": true,
  "tradeable": false,
  "news_risk": "HIGH",
  "next_event_minutes": 18.0,
  "next_event_impact": "High",
  "next_event_title": "CPI y/y",
  "macro_bias": -0.22,
  "cot_bias": 0.31,
  "sentiment_bias": 0.08,
  "trend_bias": -0.01,
  "score_adjust": 11,
  "block_trading": true,
  "block_reason": "high_impact_18m"
}
```

## Uso recomendado en el EA

- `bias`, `confidence`, `score_adjust` y `tradeable` siguen representando la capa `1H` por compatibilidad.
- Si quieres operar por horizonte, usa los campos con sufijo:
  - `bias_5m`, `confidence_5m`, `score_adjust_5m`, `tradeable_5m`, `expected_range_5m_pips`
  - `bias_1h`, `confidence_1h`, `score_adjust_1h`, `tradeable_1h`, `expected_range_1h_pips`
  - `bias_1d`, `confidence_1d`, `score_adjust_1d`, `tradeable_1d`, `expected_range_1d_pips`
- Si `block_trading == true`, no abras nuevas operaciones.
- Usa `event_block` para mostrar ventana bloqueada y `session` para filtrar por apertura, overlap o fix.
- Reconsulta cada 1 a 5 minutos; no hace falta hacerlo en cada tick.

## Estrategia automatica actual

El EA principal `examples/Atlas.mq4` opera por defecto con confirmacion triple:

- `RequireTripleAlignment = true`
- `RequireLocalConfirmation = false`
- Solo abre compra si `bias_5m == bias_1h == bias_1d == "UP"`.
- Solo abre venta si `bias_5m == bias_1h == bias_1d == "DOWN"`.
- No abre si cualquiera de las tres capas queda en `NEUTRAL` o si hay bloqueo por noticias.
- Con `RequireLocalConfirmation = false`, la entrada la decide la triple alineacion de la API; la tecnica local queda como apoyo para Monte Carlo y gestion.
- Si cambias `RequireLocalConfirmation = true`, tambien exige que el score tecnico/local supere `OperateThreshold`.
- Si `CloseOnApiDisagreement = true`, cierra una operacion abierta cuando la API pierde la alineacion triple, aparece bloqueo externo o la API cae con `RequireApiForTrading = true`.

Gestion de riesgo del EA:

- `EmergencyStopPips` limita el stop loss maximo de emergencia.
- `TrailingStartPips` define desde cuantos pips de ganancia empieza el trailing.
- `TrailingStopPips` define la distancia del trailing stop.
- `TrailingStepPips` evita modificar la orden por movimientos demasiado pequenos.
- `CountdownSec = 0` usa el cierre automatico del horizonte activo: `5M`, `1H` o `1D`.

## Seguridad

Si defines `MT4_API_KEY` en `.env`, envia el header `X-API-Key` desde el cliente.

## Configuracion WebRequest en MT4

En `Tools > Options > Expert Advisors`, agrega la URL base que MT4 acepta:

```text
http://127.0.0.1:8000/
```

En los inputs del EA deja:

```text
DataApiUrl = http://127.0.0.1:8000/
BackupDataApiUrl =
DataApiPath =
UseFlatApiUrl = true
```

El EA construye internamente una URL plana para MT4, por ejemplo `http://127.0.0.1:8000/?symbol=EURUSD`.
El endpoint tradicional `http://127.0.0.1:8000/mt4/context/EURUSD` sigue disponible para navegador, pruebas y otros clientes.

## MetaTrader 4

Hay ejemplos de consumo en:

- `examples/Atlas.mq4`
- `examples/AtlasContextClient.mq4`
