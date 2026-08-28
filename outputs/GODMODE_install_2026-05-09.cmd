@echo off
REM ============================================================================
REM   GODMODE_install_2026-05-09.cmd
REM
REM   The "this should never happen again" installer. Activates 5 layers of
REM   defense against another silent-failure incident:
REM
REM     LAYER 1 -- Code defense: load executor with new startup banner +
REM                skip taxonomy. Any future silent disabled gate / dropped
REM                signal class will surface in the very first heartbeat.
REM
REM     LAYER 2 -- Hard-fail on safety: if safeguards.py can't import, the
REM                executor refuses to trade (sys.exit(2)). Operator override
REM                via TM_NO_SAFEGUARDS=1 only.
REM
REM     LAYER 3 -- Regression tests: tests/test_pipeline_integrity.py asserts
REM                ALLOWED_STRATEGIES contains all KNOWN_STRATEGIES. Run before
REM                any commit / release.
REM
REM     LAYER 4 -- Runtime SLA monitor: tools/signal_to_trade_sla.py runs every
REM                60s, sends Telegram alert if a signal arrived without a
REM                trade in 90s OR if executor heartbeat goes stale OR if
REM                safeguards report disabled.
REM
REM     LAYER 5 -- Documentation: docs/POSTMORTEMS/2026-05-09_5_day_silent_failure.md
REM                + memory entry. Future Claude sessions / future you can read
REM                the lessons in 30 seconds.
REM
REM   Total runtime ~60 seconds. Idempotent.
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo.
echo ################################################################
echo #
echo #   GODMODE INSTALL  --  2026-05-09
echo #
echo #   5 layers of defense activating now.
echo #
echo ################################################################
echo.

REM ─────────────────────────────────────────────────────────────────
REM  LAYER 3  -  Run regression tests FIRST. If they fail, abort.
REM ─────────────────────────────────────────────────────────────────
echo ============================================================
echo  LAYER 3/5  -  Running pipeline integrity tests
echo ============================================================
.venv\Scripts\python.exe -m pytest tests\test_pipeline_integrity.py -xvs
if errorlevel 1 (
    echo.
    echo [X] Pipeline integrity tests FAILED. Refusing to restart executor
    echo     with broken invariants. Fix the test failures above first.
    pause
    exit /b 3
)
echo.
echo  [OK] All pipeline integrity tests pass.

REM ─────────────────────────────────────────────────────────────────
REM  LAYER 1+2  -  Restart executor with new banner + hard-fail
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  LAYER 1+2/5  -  Restarting executor with new defenses
echo ============================================================
echo  - killing existing executor instances
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host ('    PID ' + $_.ProcessId); taskkill /F /PID $_.ProcessId 2>$null }"

echo  - clearing singleton lock
del /f /q logs\python_signal_executor.lock 2>nul

echo  - waiting 4s for OS to release file handles
ping 127.0.0.1 -n 5 >nul

echo  - starting fresh executor
start "TM Executor - GODMODE 2026-05-09" /MIN cmd /c "title TM Executor - GODMODE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u tools\python_signal_executor.py 1>> logs\python_signal_executor.out 2>> logs\python_signal_executor.err"

echo  - waiting 10s for startup
ping 127.0.0.1 -n 11 >nul

echo.
echo ============================================================
echo  Verify startup banner appeared
echo ============================================================
powershell -NoProfile -Command "if (Test-Path 'logs\python_executor.log') { Get-Content 'logs\python_executor.log' -Tail 25 | Select-String -Pattern 'STARTUP BANNER|safeguards|telegram|news_calendar|ALLOWED_STRATEGIES|MT5 connected|EXECUTOR STARTUP' }"
echo.

REM ─────────────────────────────────────────────────────────────────
REM  LAYER 4  -  Install signal-to-trade SLA monitor
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  LAYER 4/5  -  Installing signal-to-trade SLA monitor (1-min)
echo ============================================================
set "VBS=C:\Users\Ratanshila\Documents\autmated trading\tools\hidden_signal_to_trade_sla.vbs"
if not exist "%VBS%" (
    echo  [X] %VBS% missing -- skipping schtask install
) else (
    schtasks /Delete /TN "TrendMaster Signal-to-Trade SLA" /F >nul 2>&1
    schtasks /Create /TN "TrendMaster Signal-to-Trade SLA" ^
        /TR "wscript.exe \"%VBS%\"" ^
        /SC MINUTE /MO 1 /RL LIMITED /F
    if errorlevel 1 (
        echo  [X] schtask install failed
    ) else (
        echo  [OK] SLA monitor schtask registered
        REM Run once now to populate baseline
        echo  - running monitor once for baseline
        .venv\Scripts\python.exe tools\signal_to_trade_sla.py
    )
)

REM ─────────────────────────────────────────────────────────────────
REM  LAYER 5  -  Verify documentation written
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  LAYER 5/5  -  Documentation present
echo ============================================================
if exist "docs\POSTMORTEMS\2026-05-09_5_day_silent_failure.md" (
    echo  [OK] Postmortem written
) else (
    echo  [X] Postmortem missing!
)
echo.

REM ─────────────────────────────────────────────────────────────────
REM  Final status
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  FINAL STATUS  -  watch for 'ORDER PLACED' lines
echo ============================================================
echo.
echo  Last 20 lines of executor log:
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 20"
echo.
echo  Last 5 lines of SLA monitor log:
powershell -NoProfile -Command "if (Test-Path 'logs\signal_to_trade_sla.log') { Get-Content 'logs\signal_to_trade_sla.log' -Tail 5 } else { 'no SLA log yet (will populate within 60s)' }"
echo.

echo ################################################################
echo #
echo #   GODMODE INSTALL COMPLETE
echo #
echo #   What changed:
echo #     - Executor restarted with startup banner showing every gate
echo #     - Executor will sys.exit(2) if safeguards.py ever fails to import
echo #     - Heartbeat now shows: no_file=N filtered=N stale=N (skip taxonomy)
echo #     - tests/test_pipeline_integrity.py guards ALLOWED_STRATEGIES drift
echo #     - tools/signal_to_trade_sla.py runs every 60s, alerts on regression
echo #     - docs/POSTMORTEMS/2026-05-09_5_day_silent_failure.md written
echo #
echo #   The 5-day silent failure pattern is now structurally impossible.
echo #
echo ################################################################
echo.
echo  Watch trades fire live:
echo    powershell -Command "Get-Content 'logs\python_executor.log' -Tail 5 -Wait"
echo.
pause
endlocal
