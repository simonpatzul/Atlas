# Despliegue Docker de ATLAS

## Qué levanta

- `frontend`: la página React en `nginx`
- `backend`: la API FastAPI de `atlas-data`
- `nginx` también hace proxy de la API, así que web y API salen por una sola URL

## Arranque

Desde la raíz del proyecto:

```powershell
docker compose up --build
```

Quedará disponible en:

- Web: `http://localhost:8080`
- API health: `http://localhost:8080/health`
- API MT4: `http://localhost:8080/mt4/context/EURUSD`

## Para usarlo desde MT4

No apuntes a `localhost` si tu terminal no lo acepta. Usa la IP de la máquina donde corre Docker.

Ejemplo:

- URL permitida en MT4: `http://192.168.1.25:8080`
- `DataApiUrl` del EA: `http://192.168.1.25:8080/mt4/context/`

Puedes obtener tu IP local en Windows con:

```powershell
ipconfig
```

Busca la `IPv4 Address` de tu adaptador activo.

## Variables y claves

El contenedor backend toma sus variables desde `atlas-data/.env`.

Campos relevantes:

- `FRED_API_KEY`
- `ALPHA_API_KEY`
- `MT4_API_KEY`
- `BLOCK_HIGH_IMPACT_MINUTES`
- `BLOCK_MEDIUM_IMPACT_MINUTES`

## Comandos útiles

```powershell
docker compose up --build -d
docker compose logs -f
docker compose down
```
