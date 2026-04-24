@echo off
REM ====================================================================
REM  TrendMaster v14 launcher — Sumit / 2026-04-22
REM  Starts the Python AI brain as a background process.
REM  EA runs separately inside MT5 (see INSTALL_v14.md).
REM ====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ======================================================================
echo   TrendMaster v14 - AI brain launcher
echo ======================================================================
echo.

REM ---- Activate project venv if present ------------------------------
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
    echo [OK] venv activated: .venv\Scripts\python.exe
) else (
    echo [i] No .venv found - using system Python on PATH.
)

REM ---- Verify python is callable -------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] 'python' command not found on PATH.
    echo     Install Python 3.10+ or create .venv in this folder.
    goto :fail
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo [i] %%v

REM ---- Preflight: required packages ----------------------------------
python -c "import pandas, numpy, MetaTrader5" >nul 2>&1
if errorlevel 1 (
    echo [!] Missing core dependency. Installing pandas numpy MetaTrader5 ...
    python -m pip install --quiet pandas numpy MetaTrader5
    if errorlevel 1 (
        echo [X] pip install failed. Check network / pip.
        goto :fail
    )
)

python -c "import lightgbm" >nul 2>&1
if errorlevel 1 (
    echo [i] LightGBM not found - brain will use rule-based fallback.
    echo     Install later with:  pip install lightgbm
)

REM ---- Preflight: v14 settings present --------------------------------
python -c "from config import settings as s; assert hasattr(s,'TRENDMASTER_V14'), 'settings.TRENDMASTER_V14 missing'" >nul 2>&1
if errorlevel 1 (
    echo [X] config\settings.py missing TRENDMASTER_V14 block.
    echo     See TRENDMASTER_v14_GUIDE.md
    goto :fail
)

REM ---- Preflight: brain module exists --------------------------------
if not exist "ai_trading_agents\trend_master_brain.py" (
    echo [X] ai_trading_agents\trend_master_brain.py not found.
    goto :fail
)

REM ---- Preflight: stop any stale brain -------------------------------
if exist "logs\brain.pid" (
    set /p STALE=<logs\brain.pid
    if not "!STALE!"=="" (
        echo [i] Killing stale brain PID !STALE!
        taskkill /PID !STALE! /F /T >nul 2>&1
    )
    del /q logs\brain.pid >nul 2>&1
)

REM ---- Clear legacy env vars -----------------------------------------
set ALLOW_LEGACY_MAIN=
set ALLOW_LEGACY_SWARM=
set PYTHONUNBUFFERED=1

if not exist "logs" mkdir logs

echo [OK] Dependencies and settings look good.
echo Starting brain in a VISIBLE window so you can see it running...
echo.

REM ---- Launch brain in its OWN visible window ------------------------
REM The brain runs in a normal cmd window titled "TrendMaster Brain".
REM Closing that window stops the brain. Logs also written to disk.
start "TrendMaster Brain - LIVE (do not close to keep trading)" cmd /k "title TrendMaster Brain - LIVE && python -u ai_trading_agents\trend_master_brain.py 2^> logs\trend_master_brain.err"
if errorlevel 1 (
    echo [X] Failed to spawn brain window.
    goto :fail
)

REM ---- Wait a moment then capture PID --------------------------------
timeout /t 4 /nobreak >nul
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object -First 1; if ($p) { $p.ProcessId | Out-File 'logs\brain.pid' -Encoding ascii; Write-Host ('Brain PID: ' + $p.ProcessId) } else { Write-Host 'PID capture failed - brain may still be starting.' }"

echo.
echo ======================================================================
echo   [OK] TrendMaster v14 brain ka window khul gaya hai.
echo.
echo   - Brain ka window dikhe -^> "TrendMaster Brain - LIVE" titled cmd.
echo     Use band MAT karo - wahi trading brain hai.
echo   - Stop:  STOP_TRENDMASTER_v14.bat double-click karo, OR
echo            brain ka cmd window band kar do.
echo   - Logs:  logs\trend_master_brain.err
echo   - MT5:   alag se EA chart par attach karna hoga.
echo ======================================================================
echo.
echo Press any key to close THIS launcher window. Brain ka window
echo alag se chalta rahega.
pause >nul
endlocal
exit /b 0

:fail
echo.
echo ==================== STARTUP FAILED ====================
echo Press any key to close this window.
pause >nul
endlocal
exit /b 1
