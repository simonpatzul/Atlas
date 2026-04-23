# Publicar ATLAS gratis en Vercel

Vercel Hobby es la alternativa gratuita recomendada si Koyeb o Render piden pago inicial. Vercel soporta FastAPI con Python Functions.

## 1. Crear cuenta

1. Entra a `https://vercel.com`.
2. Inicia sesion con GitHub.
3. Autoriza acceso al repo:

```text
simonpatzul/Atlas
```

## 2. Importar proyecto

1. En Vercel pulsa `Add New`.
2. Elige `Project`.
3. Importa:

```text
simonpatzul/Atlas
```

4. Framework Preset:

```text
Vite
```

5. Build Command:

```text
npm run build
```

6. Output Directory:

```text
dist
```

## 3. Variables de entorno

En `Environment Variables`, agrega:

```text
VITE_ATLAS_API_BASE=/api
CORS_ORIGINS=*
CACHE_DB=/tmp/atlas-cache.db
```

Opcionales:

```text
FRED_API_KEY=tu_key
ALPHA_API_KEY=tu_key
MT4_API_KEY=
```

Para probar con MT4 mas facil, deja `MT4_API_KEY` vacia.

## 4. Deploy

Pulsa `Deploy`.

Vercel te dara una URL parecida a:

```text
https://atlas.vercel.app/
```

## 5. Probar

Abre:

```text
https://TU-PROYECTO.vercel.app/
https://TU-PROYECTO.vercel.app/api/health
https://TU-PROYECTO.vercel.app/api/?symbol=EURUSD
```

La URL importante para MT4 es:

```text
https://TU-PROYECTO.vercel.app/api/?symbol=EURUSD
```

Debe devolver JSON con:

```text
bias_5m
bias_1h
bias_1d
confidence_5m
confidence_1h
confidence_1d
```

## 6. Configurar MT4

En MetaTrader:

1. `Tools`
2. `Options`
3. `Expert Advisors`
4. Activa `Allow WebRequest for listed URL`
5. Agrega la URL base con slash final:

```text
https://TU-PROYECTO.vercel.app/api/
```

En los inputs del EA:

```text
DataApiUrl = https://TU-PROYECTO.vercel.app/api/
BackupDataApiUrl =
DataApiPath =
UseFlatApiUrl = true
UseDataApi = true
RequireApiForTrading = true
RequireTripleAlignment = true
ShowStatusPanel = true
```

Si usas `MT4_API_KEY`, pon el mismo valor en:

```text
DataApiKey = TU_API_KEY
```

## Nota

Vercel usa funciones serverless. Puede haber cold start, pero para consultas periodicas de MT4 deberia ser suficiente para demo/prototipo.
