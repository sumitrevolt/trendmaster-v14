@echo off
REM ============================================================
REM  Install Windows Scheduled Task: walk-forward R&D harness
REM
REM  Runs daily at 08:00 LOCAL time. Iterates all 19 historical
REM  CSVs, runs run_ea_parity_backtest, writes per-symbol edge
REM  report to reports/walkforward/<DATE>.{md,json}.
REM
REM  No Telegram alerts (this is an R&D feed, not an operator
REM  alert). The Claude-side "trendmaster-rd-digest" scheduled
REM  task at 09:30 reads the JSON and produces a human digest.
REM
REM  Run once as administrator (or current-user; user-tier tasks
REM  succeed without UAC because the action runs as the user).
REM ============================================================
setlocal

set ROOT=%~dp0

echo.
echo Installing daily walkforward_lab task...
echo ROOT=%ROOT%
echo.

schtasks /create /f /sc daily /st 08:00 ^
    /tn "TrendMaster Walkforward Lab" ^
    /tr "%ROOT%tools\run_walkforward_lab.cmd"
if errorlevel 1 (
    echo [X] walkforward_lab task failed to register
    endlocal & exit /b 1
) else (
    echo [OK] walkforward_lab task registered
)

echo.
echo == Current task ==
schtasks /query /fo LIST /tn "TrendMaster Walkforward Lab" 2>nul | findstr /i "TaskName Next"

echo.
echo Done. Manual run:  schtasks /run /tn "TrendMaster Walkforward Lab"
endlocal
