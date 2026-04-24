@echo off
REM ====================================================================
REM  INSTALL_DESKTOP_ICON.bat
REM  ---------------------------------------------------------------
REM  Cleans up duplicate / legacy trading-bot shortcuts on the Desktop
REM  and installs ONE clean "Sumit AI Trading System" shortcut.
REM
REM  Just double-click this file. No admin required.
REM ====================================================================
setlocal
cd /d "%~dp0"

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "SCRIPT=%~dp0tools\install_desktop_icon.ps1"

if not exist "%SCRIPT%" (
    echo [X] Helper script not found:
    echo     %SCRIPT%
    echo Re-check the project folder.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   Cleaning duplicate desktop shortcuts and installing one clean icon
echo ======================================================================
echo.

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -ProjectRoot "%~dp0."
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] All done. Desktop par sirf ek "Sumit AI Trading System" icon hai.
) else (
    echo [X]  Installer reported error code %RC%. Check the messages above.
)
echo.
pause
endlocal
exit /b %RC%
