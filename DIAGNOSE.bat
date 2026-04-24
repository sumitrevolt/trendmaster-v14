@echo off
REM ====================================================================
REM  DIAGNOSE.bat — full preflight report, stays open.
REM  Run this if START_TRENDMASTER_v14.bat closes without a clear error.
REM ====================================================================
setlocal
cd /d "%~dp0"
color 0E

echo.
echo ======================================================================
echo   TrendMaster v14 - Diagnostic Report
echo ======================================================================
echo   Folder: %CD%
echo   Time  : %DATE% %TIME%
echo.

echo [1/8] Python on PATH?
where python 2>nul
if errorlevel 1 echo     [X] python NOT on PATH
echo.

echo [2/8] Project venv present?
if exist ".venv\Scripts\python.exe" (
    echo     [OK] .venv\Scripts\python.exe
    .venv\Scripts\python.exe --version
) else (
    echo     [X] .venv missing - run: python -m venv .venv
)
echo.

echo [3/8] Activating venv (if present) for remaining checks...
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
echo.

echo [4/8] Core imports (pandas / numpy / MetaTrader5)...
python -c "import pandas, numpy; print('   pandas ', pandas.__version__); print('   numpy  ', numpy.__version__)" 2>&1
python -c "import MetaTrader5; print('   MT5    ', MetaTrader5.__version__)" 2>&1
echo.

echo [5/8] TRENDMASTER_V14 settings block present?
python -c "from config import settings as s; print('   [OK]' if hasattr(s,'TRENDMASTER_V14') else '   [X] missing')" 2>&1
echo.

echo [6/8] Brain file present?
if exist "ai_trading_agents\trend_master_brain.py" (
    echo     [OK] ai_trading_agents\trend_master_brain.py
) else (
    echo     [X] ai_trading_agents\trend_master_brain.py NOT FOUND
)
echo.

echo [7/8] Stale PID / running brain?
if exist "logs\brain.pid" (
    set /p STALE=<logs\brain.pid
    echo     logs\brain.pid exists - PID !STALE!
    tasklist /FI "PID eq !STALE!" 2>nul | find "!STALE!"
) else (
    echo     No logs\brain.pid - brain not currently tracked.
)
echo.

echo [8/8] Last 25 lines of logs\trend_master_brain.err
if exist "logs\trend_master_brain.err" (
    echo     ------------------------------------------------------------
    powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.err' -Tail 25"
    echo     ------------------------------------------------------------
) else (
    echo     (no error log yet - brain hasn't run)
)
echo.

echo ======================================================================
echo   Copy this output if you need help - especially step 4 and step 8.
echo ======================================================================
echo.
pause
endlocal
