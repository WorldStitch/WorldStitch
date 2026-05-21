@echo off
title WorldStitch Dev Console
cd /d "%~dp0"

echo Activating Python virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate
) else (
    echo WARNING: .venv not found. Run: python -m venv .venv
    echo Then: pip install -r requirements.txt
)

echo.
echo WorldStitch Dev Console
echo ------------------------
echo Python: %VIRTUAL_ENV%
echo.

if exist "C:\Program Files\Microsoft VS Code\Code.exe" (
    echo Opening VS Code...
    start "" "C:\Program Files\Microsoft VS Code\Code.exe" .
) else if exist "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" (
    echo Opening VS Code...
    start "" "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" .
) else (
    echo VS Code not found at default locations - opening Explorer instead
    explorer .
)

cmd /k
