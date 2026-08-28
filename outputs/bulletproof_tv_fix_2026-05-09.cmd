@echo off
REM ============================================================================
REM   bulletproof_tv_fix_2026-05-09.cmd  -  No-trades issue, FINAL fix
REM
REM   Previous attempts assumed recreate_with_login.py worked. This time we:
REM     1. VERIFY current TV state via API (verify_alert_messages.py)
REM     2. Capture every output to a log file (recreate_with_login.py prints
REM        only to stdout - no proof it ran without log capture)
REM     3. RE-VERIFY after recreate - fail loudly if alerts STILL broken
REM     4. Wait for next signal and confirm via tv_plot_values.jsonl
REM     5. Install regression monitor that detects "alert delivered, no trade"
REM
REM   Run output captured to: logs\tv_alert_setup\bulletproof_<TS>.log
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Build a timestamp using PowerShell (wmic is deprecated)
for /f "delims=" %%a in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd_HHmm')"') do set "TS=%%a"

mkdir "logs\tv_alert_setup" 2>nul
set "RUNLOG=logs\tv_alert_setup\bulletproof_%TS%.log"

echo === bulletproof TV fix run %DATE% %TIME% ===  > "%RUNLOG%"
echo. >> "%RUNLOG%"

echo.
echo ============================================================
echo  STEP 1/5  -  VERIFY current TV alert state (read-only)
echo ============================================================
echo  Run log: %RUNLOG%
echo.
echo --- STEP 1: VERIFY -- >> "%RUNLOG%"
.venv\Scripts\python.exe tools\tv_alert_setup\verify_alert_messages.py >> "%RUNLOG%" 2>&1
set RC1=%ERRORLEVEL%
type "%RUNLOG%"
echo.
echo Verify exit code: %RC1% (0=all good, 1=some BAD, 2=session expired)
echo.

if %RC1% EQU 0 (
    echo ============================================================
    echo  TV alerts ALREADY have plot template - no recreate needed.
    echo  Going to verification of pipeline.
    echo ============================================================
    goto :step_verify_pipeline
)

if %RC1% EQU 2 (
    echo ============================================================
    echo  TV session expired - cannot list alerts headlessly.
    echo  Falling through to recreate_with_login.py (handles login).
    echo ============================================================
)

echo.
echo ============================================================
echo  STEP 2/5  -  RECREATE alerts (verbose, output captured)
echo ============================================================
echo  Browser will open. If TV asks to login, sign in.
echo  Script auto-detects when login succeeds and proceeds.
echo.
echo --- STEP 2: RECREATE -- >> "%RUNLOG%"
.venv\Scripts\python.exe tools\tv_alert_setup\recreate_with_login.py >> "%RUNLOG%" 2>&1
set RC2=%ERRORLEVEL%
echo.
echo --- recreate stdout/stderr appended to %RUNLOG% ---
echo.
echo Recreate exit code: %RC2% (0=success, 2=login timeout)

if %RC2% NEQ 0 (
    echo.
    echo ============================================================
    echo  [X] RECREATE FAILED with code %RC2%
    echo.
    echo  Last 30 lines of run log:
    powershell -NoProfile -Command "Get-Content '%RUNLOG%' -Tail 30"
    echo.
    echo  Common causes:
    echo    2 = TV login timeout - re-run, sign in within 8 min
    echo    1 = capture or pine template missing
    echo ============================================================
    pause
    exit /b %RC2%
)

echo.
echo ============================================================
echo  STEP 3/5  -  RE-VERIFY after recreate
echo ============================================================
echo --- STEP 3: RE-VERIFY -- >> "%RUNLOG%"
.venv\Scripts\python.exe tools\tv_alert_setup\verify_alert_messages.py >> "%RUNLOG%" 2>&1
set RC3=%ERRORLEVEL%

echo Last 25 lines of verify run:
powershell -NoProfile -Command "Get-Content '%RUNLOG%' -Tail 25"
echo.
echo Re-verify exit code: %RC3% (0=all 20 alerts have plot template)

if %RC3% NEQ 0 (
    echo.
    echo ============================================================
    echo  [X] RE-VERIFY FAILED - TV silently stripped plot template
    echo.
    echo  This is the documented edge case in verify_alert_messages.py
    echo  lines 86-88.  TV's UI overrode the API-set message field.
    echo  Workaround: per-direction URL params (one BUY alert per pair-tf,
    echo  one SELL alert per pair-tf).  See docs comment block.
    echo ============================================================
    pause
    exit /b %RC3%
)
echo  [OK] All 20 alerts now have plot template

:step_verify_pipeline
echo.
echo ============================================================
echo  STEP 4/5  -  Wait 60s for any in-flight signal, then snapshot
echo ============================================================
echo  Looking for fresh PLOT-DIRECTION lines in tv_webhook.log...
ping 127.0.0.1 -n 61 >nul

echo.
echo  Recent tv_webhook.log entries (last 10 lines):
echo --- STEP 4: PIPELINE SNAPSHOT -- >> "%RUNLOG%"
powershell -NoProfile -Command "if (Test-Path 'logs\tv_webhook.log') { Get-Content 'logs\tv_webhook.log' -Tail 10 } else { 'no log yet' }" >> "%RUNLOG%" 2>&1
powershell -NoProfile -Command "if (Test-Path 'logs\tv_webhook.log') { Get-Content 'logs\tv_webhook.log' -Tail 10 } else { 'no log yet' }"

echo.
echo  Recent tv_plot_values.jsonl (last 5 lines):
powershell -NoProfile -Command "if (Test-Path 'logs\tv_plot_values.jsonl') { Get-Content 'logs\tv_plot_values.jsonl' -Tail 5 } else { 'no plot data yet' }"
echo.
echo  Current MT5 signal files (should be EMPTY dir or non-NONE):
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_*.json' -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('  ' + $_.Name + ' = ' + (Get-Content $_.FullName -Raw)) }"
echo.

echo ============================================================
echo  STEP 5/5  -  Install regression monitor (5-min cadence)
echo ============================================================
echo  Monitor checks:
echo    - good_alerts == 20 from verify_alert_messages.py
echo    - Last received body in tv_webhook.log starts with 'RP^|' (not '####')
echo    - Last MT5 signal file has direction != NONE
echo  If any check fails, sends Telegram alert.
echo.
.venv\Scripts\python.exe outputs\_install_signal_monitor.py >> "%RUNLOG%" 2>&1
echo.

echo ============================================================
echo  ALL DONE
echo ============================================================
echo.
echo  Run log saved to: %RUNLOG%
echo.
echo  Watch the next signal:
echo    powershell -Command "Get-Content logs\tv_webhook.log -Tail 5 -Wait"
echo.
pause
endlocal
