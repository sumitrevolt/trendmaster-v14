@echo off
REM ====================================================================
REM  TrendMaster v14 STOP — kills the background brain cleanly
REM ====================================================================
setlocal
cd /d "%~dp0"

if not exist "logs\brain.pid" (
    echo No brain.pid found. Nothing to stop.
    exit /b 0
)

set /p BRAIN_PID=<logs\brain.pid
echo Stopping brain PID %BRAIN_PID% ...
taskkill /PID %BRAIN_PID% /F /T >nul 2>&1
if errorlevel 1 (
    echo Brain process already gone.
) else (
    echo Brain stopped.
)
del /q logs\brain.pid >nul 2>&1
endlocal
