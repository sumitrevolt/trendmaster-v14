@echo off
REM =======================================================================
REM  pytest_health_check.cmd
REM  Daily pytest collection + run sentinel for TrendMaster v14.
REM
REM  Behavior:
REM    1. Run `pytest --co -q` to detect collection errors (the silent
REM       failure shape from 2026-04-24 / 2026-04-25 incidents).
REM    2. If collection fails, exit non-zero and write alert to
REM       logs/pytest_health.alert.
REM    3. Otherwise run the suite with --tb=no -q and log the summary.
REM
REM  Schedule: daily at 09:05 (5 min after zero-trades watchdog).
REM  Operator review: tail logs/pytest_health.log after morning routine.
REM =======================================================================
setlocal
pushd "%~dp0\.."
set LOG=logs\pytest_health.log
set ALERT=logs\pytest_health.alert

if not exist "logs" mkdir logs

echo === Pytest health check %DATE% %TIME% === >> "%LOG%"

REM --- Step 1: collect-only (catches the silent failure shape) ---
.venv\Scripts\python.exe -m pytest --co -q > "%TEMP%\pytest_co.tmp" 2>&1
if errorlevel 1 (
    echo *** COLLECTION ERRORS DETECTED *** >> "%LOG%"
    type "%TEMP%\pytest_co.tmp" >> "%LOG%"
    echo Collection errors at %DATE% %TIME% > "%ALERT%"
    type "%TEMP%\pytest_co.tmp" >> "%ALERT%"
    del "%TEMP%\pytest_co.tmp"
    popd
    exit /b 1
)
del "%TEMP%\pytest_co.tmp"

REM --- Step 2: full run, summarise pass/fail ---
.venv\Scripts\python.exe -m pytest --tb=no -q > "%TEMP%\pytest_run.tmp" 2>&1
type "%TEMP%\pytest_run.tmp" >> "%LOG%"
echo. >> "%LOG%"
del "%TEMP%\pytest_run.tmp"
del "%ALERT%" 2>nul

popd
exit /b 0
