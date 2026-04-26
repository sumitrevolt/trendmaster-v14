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

REM Phase B1.5 fix: schtasks /tr needs the inner path quoted for the
REM scheduler to preserve quotes around the action path (the project
REM ROOT contains a space -- "autmated trading"). Without escaping, the
REM outer cmd.exe consumes the quotes and schtasks splits the path on
REM the space, registering an action like
REM   C:\Users\Ratanshila\Documents\autmated
REM and the Tuesday 08:00 run silently fails. The \"...\" form below
REM passes a literal "%ROOT%tools\run_walkforward_lab.cmd" to schtasks.
schtasks /create /f /sc daily /st 08:00 ^
    /tn "TrendMaster Walkforward Lab" ^
    /tr "\"%ROOT%tools\run_walkforward_lab.cmd\""
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
