@echo off
title WorldStitch
cd /d "%~dp0"
call :main
echo.
echo Press any key to close.
pause >nul
exit /b

:main
echo =============================================
echo   WorldStitch Launcher
echo =============================================
echo.

set PYTHON=.venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo [ERROR] .venv not found
    exit /b 1
)
echo [OK] Python venv found

"%PYTHON%" -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing FastAPI...
    "%PYTHON%" -m pip install fastapi uvicorn email-validator
)
echo [OK] FastAPI ready

echo [..] Testing server...
"%PYTHON%" -c "import sys; sys.path.insert(0,'.'); from server.app import app; print('Server OK')"
echo [OK] Server works

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found
    exit /b 1
)
echo [OK] Node.js found

call :setup_npm
echo [OK] npm ready

echo.
echo Starting API server...
start "WorldStitch-API" /min "%PYTHON%" -m uvicorn server.app:app --host 127.0.0.1 --port 8741

call :wait_for_api
if errorlevel 1 (
    echo [ERROR] API failed to start. Aborting.
    exit /b 1
)
echo [OK] API running

echo.
echo =============================================
echo   Launching WorldStitch...
echo =============================================
echo.
pushd frontend
call npm run electron:dev
popd

taskkill /FI "WINDOWTITLE eq WorldStitch-API" /F >nul 2>&1
exit /b 0

:setup_npm
pushd frontend
if not exist "node_modules\vite" (
    echo [SETUP] Installing npm packages...
    call npm install
)
if not exist "node_modules\electron" (
    echo [SETUP] Installing Electron...
    call npm install electron@30 concurrently wait-on --save-dev
)
popd
exit /b 0

:wait_for_api
set N=0
:waitloop
if %N% GEQ 20 (
    echo [ERROR] API did not start
    exit /b 1
)
ping 127.0.0.1 -n 2 >nul
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8741/health')" >nul 2>&1
if not errorlevel 1 exit /b 0
set /a N=%N%+1
goto :waitloop
