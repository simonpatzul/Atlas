# Publicar ATLAS como pagina web

El problema con MT4 no es ATLAS: la API local responde, pero MetaTrader esta bloqueando `127.0.0.1`. La solucion practica es publicar el backend en HTTPS y usar esa URL en el EA.

## Opcion gratis recomendada

Si quieres evitar cobros, usa Koyeb Free. Sigue la guia:

```text
KOYEB_DEPLOY.md
```

## Opcion recomendada: Render

Este repo ya incluye `render.yaml` y `Dockerfile.web`. Ese despliegue publica en un solo dominio:

- la pagina web React de ATLAS
- la API `/health`, `/context`, `/market`, `/mt4/context`
- el endpoint plano para MT4 `/?symbol=EURUSD`

Pasos:

1. Sube el proyecto a GitHub.
2. En Render crea un `Blueprint` desde ese repo.
3. Render detecta `render.yaml` y crea el servicio `atlas-web`.
4. Agrega las variables secretas si las tienes:
   - `FRED_API_KEY`
   - `ALPHA_API_KEY`
   - `MT4_API_KEY`
5. Espera el deploy y copia la URL HTTPS, por ejemplo:

```text
https://atlas-web.onrender.com/
```

## Probar la API publicada

Abre en navegador:

```text
https://TU-DOMINIO/
https://TU-DOMINIO/health
https://TU-DOMINIO/?symbol=EURUSD
https://TU-DOMINIO/mt4/context/EURUSD
```

El endpoint mas compatible para MT4 es:

```text
https://TU-DOMINIO/?symbol=EURUSD
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

## Configurar el EA en MetaTrader

En `Tools > Options > Expert Advisors > Allow WebRequest`, agrega la URL base con `/` final:

```text
https://TU-DOMINIO/
```

En los inputs del EA:

```text
DataApiUrl = https://TU-DOMINIO/
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

## Frontend local apuntando a la API web

El despliegue web no necesita configurar nada extra: pagina y API quedan en el mismo dominio.

Si quieres correr el frontend local pero usando la API publicada, crea `.env` en la raiz:

```text
VITE_ATLAS_API_BASE=https://TU-DOMINIO
```

Luego:

```powershell
cmd /c npm run dev
```

Si dejas `VITE_ATLAS_API_BASE` vacio, el frontend usa las rutas locales/proxy como antes.

## Nota operativa

Si el hosting duerme por inactividad, el primer request puede tardar. Para trading automatizado conviene un plan que mantenga el servicio despierto.
