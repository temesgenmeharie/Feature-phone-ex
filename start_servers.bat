@echo off
title Feature Phone Forensics System Launcher
color 0B

echo =====================================================================
echo    STARTING FEATURE PHONE FORENSICS SYSTEM
echo =====================================================================
echo.
echo [1/2] Starting Backend FastAPI Server on http://127.0.0.1:8088 ...
start "Feature Phone - Backend API (Port 8088)" cmd /k "cd /d %~dp0backend && .\.venv\Scripts\activate.bat && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8088"

echo [2/2] Starting Frontend Vite Server on http://localhost:5173 ...
start "Feature Phone - Frontend UI (Port 5173)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Waiting for servers to initialize...
timeout /t 3 /nobreak >nul

echo Opening browser to http://localhost:5173 ...
start http://localhost:5173

echo.
echo =====================================================================
echo    Both servers are running in separate terminal windows!
echo    - Frontend: http://localhost:5173
echo    - Backend API Docs: http://127.0.0.1:8088/docs
echo    (To stop the servers, simply close their terminal windows)
echo =====================================================================
echo.
pause
