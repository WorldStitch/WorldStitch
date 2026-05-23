@echo off
echo Pulling latest WorldStitch updates from GitHub...
cd /d "%~dp0"
git checkout main
git pull origin main
echo.
echo Done! Your local files are now up to date.
pause
