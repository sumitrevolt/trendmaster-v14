@echo off
REM ============================================================
REM  Install Windows Scheduled Task: zero-trades watchdog
REM
REM  Runs daily at 09:00 LOCAL time. Posts Telegram alert if:
REM    - no closed deal in the last 24 hours, OR
REM    - model confidence distribution looks degenerate
REM      (mean near 1/3 with near-zero std across fresh signals), OR
REM    - brain state file is missing.
REM
REM  Context: after the 2026-04-24 47-day zero-trades incident,
REM  this watchdog is the single best preventative measure. See
REM  docs/POSTMORTEMS/2026-04-24_zero_trades.md.
REM
REM  Run once as administrator: right-click -> Run as admin.
REM
REM  Uninstall:
REM    schtasks /delete /tn "TrendMaster Zero Trades Watchdog" /f
REM  Run now:
REM    schtasks /run /tn "TrendMaster Zero Trades Watchdog"
REM  Suppress "OK" alerts (errors and warnings still fire):
REM    setx ZERO_TRADES_WATCHDOG_QUIET_OK 1
REM ============================================================
setlocal

set ROOT=%~dp0
set PY=%ROOT%.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo.
echo Installing zero-trades watchdog task...
echo ROOT=%ROOT%
echo PY=%PY%
echo.

schtasks /create /f /sc daily /st 09:00 ^
    /tn "TrendMaster Zero Trades Watchdog" ^
    /tr "%ROOT%tools\run_zero_trades_watchdog.cmd"
if errorlevel 1 (
    echo [X] watchdog task failed to register
    endlocal & exit /b 1
) else (
    echo [OK] watchdog task registered
)

echo.
echo == Current TrendMaster tasks ==
schtasks /query /fo LIST /tn "TrendMaster Zero Trades Watchdog" 2>nul | findstr /i "TaskName Next"

echo.
echo Done. To run immediately:
echo   schtasks /run /tn "TrendMaster Zero Trades Watchdog"
endlocal
