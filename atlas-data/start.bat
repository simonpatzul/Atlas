@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist .venv (
    echo === Creando entorno virtual ===
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: No se encontro Python. Instalalo desde python.org/downloads
        echo y marca "Add Python to PATH" durante la instalacion.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    echo === Instalando dependencias ===
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

if not exist .env (
    copy .env.example .env >nul
    echo.
    echo ============================================================
    echo  Edita atlas-data\.env con tus claves antes de continuar:
    echo    - FRED_API_KEY
    echo    - ALPHA_API_KEY
    echo ============================================================
    echo.
    pause
)

set HOST=127.0.0.1
set PORT=8000

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="HOST" set HOST=%%B
    if /I "%%A"=="PORT" set PORT=%%B
)

echo === Servidor en http://%HOST%:%PORT% ===
echo === Endpoint MT4: /mt4/context/EURUSD ===
echo === Endpoint debug: /context/EURUSD ===
echo === Ctrl+C para detener ===
uvicorn main:app --host %HOST% --port %PORT%
