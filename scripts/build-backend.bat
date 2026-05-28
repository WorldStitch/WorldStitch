@echo off
setlocal EnableDelayedExpansion

REM ── WorldStitch backend freeze script ───────────────────────────────────────
REM Produces dist\server\server.exe (onedir) using PyInstaller.
REM Run from the project root: scripts\build-backend.bat

cd /d "%~dp0.."

echo [build-backend] Working directory: %CD%

REM ── Activate venv ────────────────────────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    echo [build-backend] Activating .venv...
    call .venv\Scripts\activate.bat
) else (
    echo [build-backend] WARNING: .venv not found, using system Python
)

REM ── Ensure PyInstaller is available ──────────────────────────────────────────
python -m pip install pyinstaller --quiet
if %ERRORLEVEL% neq 0 (
    echo [build-backend] ERROR: pip install pyinstaller failed
    exit /b 1
)

REM ── Clean previous artefacts ─────────────────────────────────────────────────
if exist "dist\server"  rmdir /s /q "dist\server"
if exist "build\server" rmdir /s /q "build\server"

REM ── Freeze ───────────────────────────────────────────────────────────────────
echo [build-backend] Running PyInstaller...
python -m PyInstaller ^
  --name server ^
  --onedir ^
  --noconfirm ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.loops.asyncio ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.http.h11_impl ^
  --hidden-import uvicorn.protocols.websockets ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.protocols.websockets.websockets_impl ^
  --hidden-import uvicorn.lifespan ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import anyio._backends._asyncio ^
  --hidden-import email.mime.multipart ^
  --hidden-import email.mime.text ^
  --hidden-import sqlalchemy.dialects.sqlite ^
  --hidden-import aiosqlite ^
  scripts\server_entry.py

if %ERRORLEVEL% neq 0 (
    echo [build-backend] ERROR: PyInstaller failed
    exit /b %ERRORLEVEL%
)

echo.
echo [build-backend] Done.  Frozen backend at: dist\server\server.exe
endlocal
