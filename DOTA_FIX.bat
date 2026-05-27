@echo off
echo === Dota 2 Fix ===
echo.

echo [1/4] Killing Steam...
taskkill /f /im steam.exe 2>nul
taskkill /f /im steamwebhelper.exe 2>nul
taskkill /f /im steamservice.exe 2>nul
timeout /t 3 /nobreak >nul
echo Done.
echo.

echo [2/4] Removing read-only flags...
attrib -R "D:\STEAMLIBRARY\*" /S /D
echo Done.
echo.

echo [3/4] Fixing permissions...
icacls "D:\STEAMLIBRARY" /grant "%USERNAME%":(OI)(CI)F /T /C /Q
icacls "D:\STEAMLIBRARY\steamapps" /grant "%USERNAME%":(OI)(CI)F /T /C /Q
echo Done.
echo.

echo [4/4] Clearing download cache...
if exist "D:\STEAMLIBRARY\steamapps\downloading" (
    rd /s /q "D:\STEAMLIBRARY\steamapps\downloading"
    echo Deleted downloading folder.
) else (
    echo Already clean.
)
if exist "D:\STEAMLIBRARY\steamapps\temp" (
    rd /s /q "D:\STEAMLIBRARY\steamapps\temp"
    echo Deleted temp folder.
) else (
    echo Already clean.
)
echo.

echo === All done! ===
echo.
echo Now open Steam and right-click Dota 2 ^> Properties ^> Local Files ^> Verify integrity
echo.
pause
