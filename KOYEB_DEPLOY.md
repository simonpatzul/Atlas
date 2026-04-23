# Publicar ATLAS gratis en Koyeb

Koyeb es la opcion gratuita recomendada para ATLAS porque permite desplegar un Web Service desde GitHub usando Dockerfile.

## 1. Crear cuenta

1. Entra a `https://www.koyeb.com`.
2. Crea una cuenta.
3. Conecta tu GitHub cuando Koyeb lo pida.

## 2. Crear el servicio

1. En Koyeb, pulsa `Create Web Service`.
2. Elige `GitHub`.
3. Selecciona el repo:

```text
simonpatzul/Atlas
```

4. Branch:

```text
main
```

5. Builder:

```text
Dockerfile
```

6. Dockerfile location:

```text
Dockerfile.web
```

7. Service type:

```text
Web Service
```

8. Instance:

```text
Free
```

9. Exposed port:

```text
8000
```

10. Route:

```text
/
```

## 3. Variables de entorno

Agrega estas variables:

```text
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

Cuando termine, Koyeb te dara una URL parecida a:

```text
https://atlas-simonpatzul.koyeb.app/
```

## 5. Probar

Abre en el navegador:

```text
https://TU-APP.koyeb.app/
https://TU-APP.koyeb.app/health
https://TU-APP.koyeb.app/?symbol=EURUSD
```

La URL importante para MT4 es:

```text
https://TU-APP.koyeb.app/?symbol=EURUSD
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
https://TU-APP.koyeb.app/
```

En los inputs del EA:

```text
DataApiUrl = https://TU-APP.koyeb.app/
BackupDataApiUrl =
DataApiPath =
UseFlatApiUrl = true
UseDataApi = true
RequireApiForTrading = true
RequireTripleAlignment = true
ShowStatusPanel = true
```

## Nota importante

La instancia gratuita de Koyeb puede escalar a cero despues de inactividad. Para mantenerla despierta, MT4 consultando cada minuto deberia ayudar. Si pasa mucho tiempo sin trafico, la primera consulta puede tardar mas.
