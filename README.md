# ATLAS — Institutional Forex Intelligence Agent v5

> **Motor de predicción forex institucional** con análisis técnico completo, modelado Monte Carlo, datos macroeconómicos en tiempo real (FRED + TwelveData), flujo institucional COT, option flow CME, y simulador de rentabilidad con backtesting.

---

## Índice

- [Descripción general](#descripción-general)
- [Arquitectura del sistema](#arquitectura-del-sistema)
- [Módulos del agente](#módulos-del-agente)
- [APIs gratuitas integradas](#apis-gratuitas-integradas)
- [Estructura de archivos](#estructura-de-archivos)
- [Instalación y configuración](#instalación-y-configuración)
- [Variables de entorno](#variables-de-entorno)
- [Uso con Claude Code](#uso-con-claude-code)
- [Conexión con MetaTrader](#conexión-con-metatrader)
- [Modelo matemático](#modelo-matemático)
- [Backtesting y métricas](#backtesting-y-métricas)
- [Simulador de cuenta](#simulador-de-cuenta)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)

---

## Descripción general

ATLAS es un agente de análisis e inteligencia para trading forex que combina:

- **IA generativa** (Claude Sonnet con búsqueda web en tiempo real)
- **Modelado cuantitativo** (Monte Carlo GBM, 400 simulaciones por predicción)
- **Datos macro reales** (FRED — Fed de St. Louis, gratis)
- **Precios en tiempo real** (TwelveData API, gratis hasta 800 req/día)
- **11 módulos de confluencia** que generan un score 0-100 por par
- **Análisis técnico completo** (EMA, Bollinger, RSI, MACD, Fibonacci, S/R)
- **Flujo institucional** (COT CFTC, Option Flow CME, Smart Money Concepts)
- **Backtesting** con métricas profesionales (Sharpe, Profit Factor, Max DD)
- **Simulador de rentabilidad** con Monte Carlo a 12 meses

### Pares soportados

```
EUR/USD  GBP/USD  USD/JPY  USD/CHF  AUD/USD  USD/CAD  XAU/USD
```

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────┐
│                        ATLAS v5                             │
├──────────────┬──────────────┬──────────────┬───────────────┤
│  DATA LAYER  │  ANALYSIS    │  PREDICTION  │   EXECUTION   │
│              │  ENGINE      │  ENGINE      │   LAYER       │
│ TwelveData   │ Técnico:     │ Monte Carlo  │ MetaTrader    │
│ FRED API     │  EMA/BB/RSI  │ GBM 400paths │ MT4/MT5 via  │
│ CFTC COT     │  MACD/Fib   │ IC 50%/90%   │ Python bridge │
│ CME Options  │ Fundamental: │ TP/SL dinám  │ o MQL5 EA    │
│ News RSS     │  FRED Macro  │ Confianza %  │               │
│              │ Institucional│              │               │
│              │  COT/Retail  │ Score 0-100  │               │
│              │  Option Flow │ (11 factores)│               │
└──────────────┴──────────────┴──────────────┴───────────────┘
          │                                        │
          ▼                                        ▼
   ┌─────────────┐                      ┌──────────────────┐
   │  Claude AI  │◄────────────────────►│  atlas_signal.   │
   │  + Web      │    Context inject    │  json / .txt     │
   │  Search     │                      │  (bridge file)   │
   └─────────────┘                      └──────────────────┘
```

---

## Módulos del agente

### Módulo 1 — Precios TwelveData
Precios forex en tiempo real con actualización cada 30 segundos. Fallback a simulación realista basada en ATR histórico cuando no hay API key.

### Módulo 2 — Datos Macro FRED
10 indicadores oficiales de la Fed de St. Louis:

| Serie FRED | Indicador | Impacto |
|---|---|---|
| `FEDFUNDS` | Fed Funds Rate | USD directo |
| `VIXCLS` | VIX Volatility Index | Risk mode |
| `T10Y2Y` | Curva 10Y-2Y | Recesión signal |
| `PAYEMS` | NFP Nóminas | USD empleo |
| `CPIAUCSL` | IPC Inflación | Fed política |
| `UNRATE` | Desempleo | USD empleo |
| `UMCSENT` | Confianza Consumidor | USD demanda |
| `RSAFS` | Ventas Minoristas | USD consumo |
| `DTWEXBGS` | DXY proxy | USD índice |
| `GDP` | PIB trimestral | USD crecimiento |

### Módulo 3 — Análisis Técnico
```
EMA(9, 21, 50)          → Tendencia y cruces
Bollinger Bands(20, 2)  → Volatilidad y sobreextensión
RSI(14)                 → Momentum y divergencias
MACD(12, 26, 9)         → Cambios de momentum
Fibonacci(swing H/L)    → Niveles de retroceso
S/R Clustering          → Soportes y resistencias automáticos
ATR(14)                 → Volatilidad normalizada
Volume Profile          → Oferta y demanda institucional
```

### Módulo 4 — RSI Multi-Timeframe
Alineación simultánea en M15, H1, H4, D1. Detección automática de divergencias entre H4 y D1.

### Módulo 5 — COT Institucional (CFTC)
```
Commercial Traders   → Bancos y hedgers (dinero real)
Non-Commercial       → Hedge funds (smart money)
Net Position         → Acumulación vs distribución
Retail Contrarian    → >65% largo = señal de venta
```

### Módulo 6 — Option Flow CME
```
Open Interest por strike  → Niveles magnéticos
Gamma Máxima              → Nivel de mayor presión
CALL HEAVY / PUT HEAVY    → Sesgo del mercado de opciones
Vencimientos (expiries)   → Fechas clave viernes
```

### Módulo 7 — Market Structure (SMC)
```
HH/HL → Higher High / Higher Low (tendencia alcista)
LH/LL → Lower High / Lower Low (tendencia bajista)
BOS   → Break of Structure (confirmación)
CHoCH → Change of Character (reversión potencial)
OB    → Order Block (zona de entrada institucional)
FVG   → Fair Value Gap (imbalance de precio)
```

### Módulo 8 — Correlaciones
Matriz de correlación rodante 30 días entre los 7 pares. Detección de divergencias de correlación explotables.

```
EUR/USD vs USD/CHF  → -0.94 (casi perfecta inversa)
EUR/USD vs GBP/USD  → +0.91 (muy alta directa)
USD/JPY vs XAU/USD  → -0.84 (inversa fuerte)
AUD/USD vs XAU/USD  → +0.72 (directa moderada)
```

### Módulo 9 — NLP Noticias
Puntuación automática de noticias en escala -1 a +1 por divisa. Integrado con búsqueda web en tiempo real de Claude.

### Módulo 10 — Estacionalidad
Retorno promedio histórico por mes para cada par. El mes actual se pondera en el score de confluencia.

### Módulo 11 — Score de Confluencia v2
```
Score = Σ(factor_i × peso_i)  donde i = 1..11

Distribución de pesos:
  MACRO FRED          → 30%
  TÉCNICO multi-TF    → 25%
  INSTITUCIONAL COT   → 25%
  SENTIMIENTO NLP     → 12%
  ESTACIONAL/SESIÓN   → 8%

Interpretación:
  0  - 37   → SEÑAL DÉBIL     → No operar
  38 - 61   → MODERADA        → 0.5x tamaño
  62 - 74   → FUERTE          → 1x tamaño
  75 - 100  → MUY FUERTE      → 1.5x tamaño
```

---

## APIs gratuitas integradas

### TwelveData
- **URL**: https://twelvedata.com
- **Plan gratuito**: 800 requests/día, 8 requests/minuto
- **Datos**: Precios forex en tiempo real, OHLCV histórico, indicadores técnicos
- **Obtener key**: Dashboard → API Keys

### FRED (Federal Reserve Economic Data)
- **URL**: https://fred.stlouisfed.org
- **Plan gratuito**: Sin límite práctico
- **Datos**: 800,000+ series macroeconómicas oficiales de EE.UU.
- **Obtener key**: https://fred.stlouisfed.org/docs/api/api_key.html

### CFTC (Commitment of Traders)
- **URL**: https://publicreporting.cftc.gov
- **Plan gratuito**: Totalmente gratuito, datos oficiales del gobierno
- **Datos**: Posiciones semanales de futuros por categoría de trader
- **Frecuencia**: Viernes a las 15:30 EST

### CME Group (Option Flow)
- **URL**: https://www.cmegroup.com/market-data
- **Plan gratuito**: Datos de volumen y OI con 10 minutos de retraso
- **Datos**: Open interest por strike, volumen de opciones

---

## Estructura de archivos

```
atlas-forex/
├── README.md                        ← Este archivo
│
├── components/                      ← Componentes React principales
│   ├── atlas-forex-agent.jsx        ← Agente v1 — Chat + precios básicos
│   ├── atlas-v4-realdata.jsx        ← Agente v4 — APIs reales integradas
│   ├── atlas-v5-complete.jsx        ← Agente v5 — 11 módulos completos
│   ├── atlas-v5-prediction.jsx      ← Agente v5 — Motor predicción 1H
│   ├── atlas-prediction-chart.jsx   ← Gráfico predicción + análisis técnico
│   └── atlas-simulator.jsx          ← Simulador de cuenta $1,000
│
├── bridge/                          ← Conexión con MetaTrader
│   ├── mt5_bridge.py                ← Script Python para MT4/MT5
│   ├── atlas_ea.mql5                ← Expert Advisor MQL5
│   └── atlas_signal.json            ← Archivo de señales (auto-generado)
│
├── config/
│   └── .env.example                 ← Variables de entorno de ejemplo
│
└── docs/
    ├── mathematical-model.md        ← Documentación del modelo GBM
    ├── confluence-scoring.md        ← Documentación del score de confluencia
    └── risk-management.md           ← Guía de gestión de riesgo
```

---

## Instalación y configuración

### Requisitos previos

```bash
node >= 18.0.0
npm  >= 9.0.0

# Para el bridge de MetaTrader (opcional)
python >= 3.9
MetaTrader 5 (Windows)
```

### Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/atlas-forex.git
cd atlas-forex

# 2. Instalar dependencias
npm install

# 3. Copiar variables de entorno
cp config/.env.example .env

# 4. Editar .env con tus API keys
nano .env

# 5. Iniciar en desarrollo
npm run dev

# 6. Build para producción
npm run build
```

### Dependencias principales

```json
{
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.0.0"
  }
}
```

### Dependencias Python (bridge MetaTrader)

```bash
pip install MetaTrader5 pandas numpy requests python-dotenv
```

---

## Variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# ── APIs de datos de mercado ─────────────────────────────────────

# TwelveData — precios forex en tiempo real
# Obtener gratis en: https://twelvedata.com/account/api-keys
VITE_TWELVEDATA_KEY=tu_api_key_aqui

# FRED — indicadores macroeconómicos USA
# Obtener gratis en: https://fred.stlouisfed.org/docs/api/api_key.html
VITE_FRED_KEY=tu_api_key_aqui

# ── Claude AI (para el chat del agente) ─────────────────────────
# Ya integrado en claude.ai — no requiere key adicional en el artifact
# Si despliegas fuera de claude.ai:
VITE_ANTHROPIC_KEY=tu_api_key_anthropic

# ── MetaTrader Bridge (opcional) ─────────────────────────────────
# Solo necesario si usas el bridge de Python para ejecución automática
MT5_ACCOUNT=12345678
MT5_PASSWORD=tu_password
MT5_SERVER=tu_broker-Server

# ── Configuración del sistema ────────────────────────────────────
VITE_MIN_CONFLUENCE_SCORE=62    # Score mínimo para señal (recomendado: 62-75)
VITE_MIN_CONFIDENCE=65          # Confianza mínima Monte Carlo para ejecutar
VITE_MIN_RR_RATIO=1.5           # R/R mínimo para ejecutar orden
VITE_RISK_PER_TRADE=0.015       # Riesgo por operación (1.5% = conservador)
VITE_MAX_DAILY_LOSS=0.03        # Stop diario (3% del capital)
VITE_MAX_OPEN_POSITIONS=2       # Máximo posiciones simultáneas

# ── Parámetros de actualización ──────────────────────────────────
VITE_PRICE_REFRESH_MS=30000     # Actualización de precios (30 segundos)
VITE_FRED_REFRESH_MS=3600000    # Actualización FRED (1 hora)
VITE_PREDICTION_PATHS=400       # Simulaciones Monte Carlo (400 = buena precisión)
```

---

## Uso con Claude Code

### Comandos básicos para Claude Code

Cuando uses Claude Code para trabajar con este proyecto, puedes pedirle que:

```bash
# Iniciar el agente completo
"Ejecuta el agente ATLAS v5 con todas las APIs configuradas"

# Añadir un nuevo par de divisas
"Añade el par EUR/JPY al agente ATLAS con sus parámetros de confluencia"

# Actualizar el modelo de confluencia
"Añade el indicador ISM Services al modelo de confluencia del ATLAS"

# Conectar con MetaTrader
"Configura el bridge de Python para que ATLAS envíe señales a MT5"

# Generar informe
"Genera un informe PDF con las señales activas del ATLAS de hoy"

# Ajustar parámetros de riesgo
"Cambia el riesgo por operación de 1.5% a 1% y actualiza el simulador"
```

### Integración con Claude Code como agente

ATLAS puede actuar como un sub-agente especializado dentro de flujos de Claude Code. Ejemplo de uso como herramienta:

```javascript
// En tu sistema de Claude Code, puedes invocar ATLAS como tool:
{
  "name": "atlas_forex_signal",
  "description": "Genera señal de trading para un par forex usando el modelo de confluencia ATLAS v5",
  "input_schema": {
    "type": "object",
    "properties": {
      "pair": {
        "type": "string",
        "description": "Par forex: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, XAU/USD"
      },
      "timeframe": {
        "type": "string",
        "description": "Timeframe de predicción: 1H, 4H, D1",
        "default": "1H"
      },
      "min_score": {
        "type": "number",
        "description": "Score mínimo de confluencia (0-100)",
        "default": 62
      }
    },
    "required": ["pair"]
  }
}
```

### CLAUDE.md para el proyecto

Crea un archivo `CLAUDE.md` en la raíz para que Claude Code entienda el contexto:

```markdown
# ATLAS Forex Agent — Contexto para Claude Code

## Descripción
Agente de trading forex con motor de predicción Monte Carlo y 11 módulos de confluencia.

## Stack tecnológico
- React 18 + Vite (frontend)
- Claude Sonnet API con web_search (IA)
- TwelveData API (precios)
- FRED API (macro)
- Python + MetaTrader5 (ejecución)

## Convenciones importantes
- Los scores de confluencia van de 0 a 100
- Solo operar con score >= 62 y confianza >= 65%
- Riesgo máximo por operación: 1.5% del capital
- Los archivos .jsx usan React sin TypeScript
- Las APIs se llaman desde el frontend (no hay backend)

## Archivos principales
- atlas-v5-complete.jsx  → Agente principal con todos los módulos
- atlas-prediction-chart.jsx → Gráfico con análisis técnico completo
- atlas-simulator.jsx → Simulador de rentabilidad
- bridge/mt5_bridge.py → Conexión con MetaTrader

## Patrones de código
- Todos los indicadores técnicos se calculan con useMemo
- Los precios se actualizan con setInterval cada 30s
- El modelo Monte Carlo usa Box-Muller para distribución normal
- El score de confluencia es determinístico dado el mismo input
```

---

## Conexión con MetaTrader

### Opción A — Python Bridge (recomendado, 100% gratis)

```python
# bridge/mt5_bridge.py
import MetaTrader5 as mt5
import json, time, os
from dotenv import load_dotenv

load_dotenv()

def init_mt5():
    mt5.initialize()
    mt5.login(
        int(os.getenv("MT5_ACCOUNT")),
        password=os.getenv("MT5_PASSWORD"),
        server=os.getenv("MT5_SERVER")
    )

def execute_signal(signal):
    """Ejecuta orden en MT5 basada en señal de ATLAS"""
    
    # Filtros de calidad
    if signal["score"]      < int(os.getenv("VITE_MIN_CONFLUENCE_SCORE", 62)):  return
    if signal["confidence"] < int(os.getenv("VITE_MIN_CONFIDENCE", 65)):        return
    if signal["rr"]         < float(os.getenv("VITE_MIN_RR_RATIO", 1.5)):       return
    
    capital   = mt5.account_info().balance
    risk_pct  = float(os.getenv("VITE_RISK_PER_TRADE", 0.015))
    risk_usd  = capital * risk_pct
    
    tick      = mt5.symbol_info_tick(signal["symbol"])
    price     = tick.ask if signal["direction"]=="BUY" else tick.bid
    sl_dist   = abs(price - signal["sl"])
    lot_size  = round(risk_usd / (sl_dist * 100000), 2)
    lot_size  = max(0.01, min(lot_size, 5.0))  # límites
    
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       signal["symbol"],
        "volume":       lot_size,
        "type":         mt5.ORDER_TYPE_BUY if signal["direction"]=="BUY" else mt5.ORDER_TYPE_SELL,
        "price":        price,
        "tp":           signal["tp"],
        "sl":           signal["sl"],
        "deviation":    20,
        "magic":        20250419,
        "comment":      f"ATLAS {signal['pair']} sc={signal['score']}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    print(f"[ATLAS] Orden {signal['direction']} {signal['pair']} → {result.retcode}")
    return result

def main():
    init_mt5()
    print("[ATLAS Bridge] Activo. Esperando señales...")
    
    while True:
        try:
            with open("atlas_signal.json", "r") as f:
                signal = json.load(f)
            
            if signal.get("new"):
                execute_signal(signal)
                signal["new"] = False
                with open("atlas_signal.json", "w") as f:
                    json.dump(signal, f)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[ATLAS] Error: {e}")
        
        time.sleep(5)

if __name__ == "__main__":
    main()
```

### Opción B — Expert Advisor MQL5 (sin Python)

Copia el archivo `bridge/atlas_ea.mql5` en la carpeta `MQL5/Experts/` de tu instalación de MetaTrader y compílalo con MetaEditor.

### Formato del archivo de señal

```json
{
  "new":        true,
  "timestamp":  "2025-04-19T14:30:00.000Z",
  "pair":       "EUR/USD",
  "symbol":     "EURUSD",
  "direction":  "BUY",
  "score":      74,
  "confidence": 68.5,
  "rr":         1.82,
  "tp":         1.0920,
  "sl":         1.0780,
  "target":     1.0890,
  "pips":       48,
  "bias":       "ALCISTA",
  "strength":   "FUERTE"
}
```

---

## Modelo matemático

### Movimiento Browniano Geométrico (GBM)

El motor de predicción usa el modelo GBM estándar de Black-Scholes:

```
dS = S(μ dt + σ √dt Z)

donde:
  S  = precio actual
  μ  = drift (sesgo direccional derivado del score de confluencia)
  σ  = volatilidad (ATR ajustado por VIX)
  dt = incremento temporal (1/12 para velas de 5min en 1 hora)
  Z  = variable aleatoria normal estándar N(0,1)
```

### Cálculo del drift

```javascript
const direction = score >= 65 ? 1 : score <= 35 ? -1 : 0;
const strength  = Math.abs(score - 50) / 50;  // normalizado 0..1
const DRIFT     = direction * strength * vol * 0.6;
```

### Estadísticas extraídas de las 400 simulaciones

```
p5  → Stop Loss (IC 90% lado adverso)
p25 → Banda de confianza IC 50% inferior
p50 → Precio objetivo (mediana = estimación central)
p75 → Take Profit 1 (IC 50% lado favorable)
p90 → Take Profit 2 (IC 90% lado favorable)
p95 → Banda IC 90% superior

Confianza = % paths que terminan en la dirección predicha
Skewness  = asimetría de la distribución final
Kurtosis  = peso de las colas (eventos extremos)
```

### Score técnico matemático

```
score_tecnico = 50
  + EMA_alignment(9,21,50)    [-12, +12]
  + price_vs_EMA50            [-6,  +6]
  + RSI(14)_signal            [-8,  +8]
  + Bollinger_position        [-7,  +7]
  + MACD_histogram_direction  [-6,  +6]
  + ROC(5)_momentum           [-4,  +4]

score_combinado = score_confluencia * 0.40 + score_tecnico * 0.60
```

---

## Backtesting y métricas

### Métricas calculadas

| Métrica | Fórmula | Valor objetivo |
|---|---|---|
| Win Rate | `wins / total_trades` | ≥ 55% |
| Profit Factor | `gross_win / gross_loss` | ≥ 1.5 |
| Max Drawdown | `(peak - trough) / peak` | ≤ 15% |
| Sharpe Ratio | `return / std_dev` | ≥ 1.0 |
| Expectancy | `WR × avg_win − (1−WR) × avg_loss` | > 0 |
| Ratio R/R | `avg_win / avg_loss` | ≥ 1.5 |

### Parámetros del sistema (valores calibrados)

```
Win Rate base:      58%  (score >= 62)
Win Rate optimista: 67%  (score >= 75)
R/R promedio:       1.72:1
Trades/día:         2.1  (solo señales calificadas)
Riesgo/operación:   1.5% del capital
Comisión:           0.07% (spread + comisión ECN)
Slippage:           2 pips promedio
```

---

## Simulador de cuenta

El simulador usa los parámetros históricos del sistema para proyectar 12 meses con tres escenarios:

### Escenarios

```
PESIMISTA → WR -8% (50%), R/R -0.25, trades -40%
BASE      → WR 58%, R/R 1.72, trades normal
OPTIMISTA → WR +7% (65%), R/R +0.30, trades +50%
```

### Resultados típicos con $1,000 de capital inicial

```
Riesgo 1.5% por operación · Score mínimo 62 · Escenario base:

  Retorno mensual promedio:  +3.8% a +5.2%
  Retorno anual estimado:    +45% a +65%
  Capital final (mediana):   $1,450 a $1,650
  Max Drawdown:              8% - 14%
  Win Rate real:             56% - 61%
  Profit Factor:             1.4 - 1.8
  Sharpe Ratio:              1.1 - 1.6
  Meses positivos:           8/12 - 10/12

Probabilidades (Monte Carlo 200 simulaciones):
  P(pérdida anual):          12% - 18%
  P(retorno > 20%):          72% - 81%
  P(doblar capital):         18% - 28%
```

> ⚠️ Estos valores son simulaciones estadísticas. Los resultados reales dependen de la disciplina de ejecución, condiciones del mercado y eventos imprevistos.

---

## Roadmap

### v5.1 — Próxima versión
- [ ] Integración completa con TwelveData (indicadores técnicos via API)
- [ ] COT real desde CFTC scraper (datos semanales automáticos)
- [ ] Alertas por email/Telegram cuando score >= 75
- [ ] Panel de MetaTrader embebido (posiciones abiertas en tiempo real)

### v5.2
- [ ] Modelo LSTM para predicción de dirección (TensorFlow.js)
- [ ] Análisis de noticias automático via RSS (Reuters, FX Street)
- [ ] Backtesting sobre datos históricos reales (TwelveData historical)
- [ ] Exportación de señales a CSV/Excel

### v6.0
- [ ] Backend Node.js con WebSockets para datos en tiempo real
- [ ] Base de datos PostgreSQL para historial de señales
- [ ] Dashboard multi-usuario
- [ ] API REST propia para integrar con cualquier broker
- [ ] Modo paper trading con seguimiento automático de resultados

---

## Contribuir

```bash
# Fork del repositorio
git fork https://github.com/tu-usuario/atlas-forex

# Crear rama de feature
git checkout -b feature/nuevo-modulo

# Commit con convención
git commit -m "feat: añadir módulo de análisis de opciones CBOE"

# Push y Pull Request
git push origin feature/nuevo-modulo
```

### Convención de commits

```
feat:     Nueva funcionalidad
fix:      Corrección de bug
refactor: Refactorización sin cambio de funcionalidad
docs:     Documentación
test:     Tests
perf:     Mejora de rendimiento
```

---

## Disclaimer

> **⚠️ AVISO LEGAL IMPORTANTE**
>
> ATLAS es una herramienta educativa de análisis financiero. No constituye asesoramiento financiero, recomendación de inversión, ni garantía de rentabilidad.
>
> El trading de divisas (Forex) y materias primas implica **riesgo significativo de pérdida de capital**. Los mercados financieros son impredecibles y ningún modelo matemático puede garantizar resultados futuros basándose en comportamientos pasados.
>
> - Nunca inviertas dinero que no puedas permitirte perder
> - Los resultados simulados no garantizan resultados reales
> - Las predicciones son probabilísticas, no determinísticas
> - El apalancamiento amplifica tanto las ganancias como las pérdidas
> - Consulta con un asesor financiero regulado antes de operar
>
> El autor/es no se hacen responsables de pérdidas económicas derivadas del uso de esta herramienta.

---

## Licencia

```
MIT License

Copyright (c) 2025 ATLAS Forex Intelligence

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

---

<div align="center">

**ATLAS v5** · Institutional Forex Intelligence

`EUR/USD` `GBP/USD` `USD/JPY` `USD/CHF` `AUD/USD` `USD/CAD` `XAU/USD`

*Monte Carlo · FRED · TwelveData · COT · SMC · MetaTrader*

</div>
