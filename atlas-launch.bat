@echo off
setlocal

set "ROOT=C:\Users\oscar\Documents\Claude"
set "BACKEND=%ROOT%\atlas-data"

start "ATLAS Backend" cmd /k "cd /d %BACKEND% && call .\.venv\Scripts\activate.bat && uvicorn main:app --host 127.0.0.1 --port 8000"
start "ATLAS Frontend" cmd /k "cd /d %ROOT% && npm run dev"

timeout /t 5 /nobreak >nul
start "" http://localhost:5173
