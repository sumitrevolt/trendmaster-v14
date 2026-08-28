@echo off
REM ============================================================================
REM   nuke_all_popups_2026-05-09.cmd
REM
REM   FINAL fix for the recurring terminal popups. The previous fixes targeted
REM   only 5 schtasks but missed the actual culprits. This time:
REM
REM   - Re-registers EVERY schtask that has a corresponding hidden_*.vbs wrapper
REM   - Idempotent — re-running this is safe
REM   - Verbose: prints the BEFORE/AFTER of each task's "Task To Run" line
REM
REM   Schtasks fixed (each pointed at its hidden_*.vbs wrapper or pythonw.exe):
REM     1.  TrendMaster TV Webhook Watchdog       (every 5 min — PRIMARY popup)
REM     2.  TrendMaster Junction Guard            (every 15 min — DOUBLE flash)
REM     3.  TrendMaster Schtasks Audit            (every 30 min)
REM     4.  TrendMaster Process Watchdog          (already silent — re-applied)
REM     5.  TrendMaster Brain Watchpet            (already silent — re-applied)
REM     6.  TrendMaster Health Watchdog           (already silent — re-applied)
REM     7.  TrendMaster Zero Trades Watchdog      (already silent — re-applied)
REM     8.  TrendMaster Master Autostart          (already silent — re-applied)
REM     9.  TrendMaster Daily Maintenance         (already silent — re-applied)
REM    10.  TrendMaster Reactivate Alerts         (already silent — re-applied)
REM    11.  TrendMaster News Calendar Refresh     (already silent — re-applied)
REM    12.  TrendMaster TV Alert Renewer          (pythonw — re-applied)
REM    13.  TrendMaster Hourly Snapshot           (pythonw — re-applied)
REM    14.  TrendMaster Daily Summary             (pythonw — re-applied)
REM    15.  TrendMaster Pytest Health Check       (VBS — re-applied)
REM    16.  TrendMaster Code Graph Rebuild        (VBS)
REM    17.  TrendMaster Events Rotator            (VBS)
REM    18.  TrendMaster Watch-Pets                (VBS)
REM    19.  TrendMaster Alert Bridge              (VBS)
REM    20.  TrendMaster Brain Liveness            (VBS)
REM    21.  TrendMaster Local Signal Generator    (VBS)
REM    22.  TrendMaster Signal Outcome Collector  (VBS)
REM    23.  TrendMaster Live Dashboard            (VBS)
REM    24.  TrendMaster Auto Research             (VBS)
REM    25.  TrendMaster EA Parity Nightly         (VBS)
REM    26.  TrendMaster Walkforward Lab           (VBS)
REM    27.  OpenClaw Gateway                      (~/.openclaw/hidden_gateway.vbs)
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

set "TOOLS=C:\Users\Ratanshila\Documents\autmated trading\tools"
set "PYW=C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\pythonw.exe"
set "OUTLOG=outputs\_session_scratch\nuke_popups_run.log"
mkdir "outputs\_session_scratch" 2>nul
echo === nuke_all_popups run %DATE% %TIME% === > "%OUTLOG%"

REM Helper macro: register a schtask using a hidden VBS wrapper, MINUTE schedule
REM Args: task-name, vbs-name, /MO interval-min
call :register_vbs_min "TrendMaster TV Webhook Watchdog"      hidden_tv_webhook_watchdog.vbs   5
call :register_vbs_min "TrendMaster Junction Guard"           hidden_junction_guard.vbs        15
call :register_vbs_min "TrendMaster Schtasks Audit"           hidden_schtasks_audit.vbs        30
call :register_vbs_min "TrendMaster Process Watchdog"         hidden_process_watchdog.vbs      2
call :register_vbs_min "TrendMaster Brain Watchpet"           watchpet_brain_alive.vbs         5
call :register_vbs_min "TrendMaster Pytest Health Check"      hidden_pytest_health_check.vbs   240
call :register_vbs_min "TrendMaster Signal Outcome Collector" hidden_signal_outcome_collector.vbs 5
call :register_vbs_min "TrendMaster Watch-Pets"               hidden_watch_pets.vbs            5
call :register_vbs_min "TrendMaster Brain Liveness"           hidden_brain_liveness.vbs        5
call :register_vbs_min "TrendMaster Alert Bridge"             hidden_alert_bridge.vbs          5
call :register_vbs_min "TrendMaster Code Graph Rebuild"       hidden_code_graph_rebuild.vbs    30
call :register_vbs_min "TrendMaster Events Rotator"           hidden_events_rotator.vbs        60
call :register_vbs_min "TrendMaster Local Signal Generator"   hidden_local_signal_generator.vbs 5
call :register_vbs_min "TrendMaster Live Dashboard"           hidden_dashboard.vbs             5

REM Daily / hourly tasks
call :register_vbs_daily "TrendMaster Zero Trades Watchdog"   hidden_zero_trades_watchdog.vbs  09:00
call :register_vbs_daily "TrendMaster Daily Maintenance"      daily_maintenance.vbs            23:50
call :register_vbs_daily "TrendMaster Auto Research"          hidden_auto_research.vbs         04:00
call :register_vbs_daily "TrendMaster Morning Routine"        hidden_morning_routine.vbs       08:30

REM Weekly tasks (every 7 days at fixed time)
call :register_vbs_weekly "TrendMaster Walkforward Lab"       hidden_walkforward_lab.vbs       SAT 02:00
call :register_vbs_weekly "TrendMaster News Calendar Refresh" refresh_news_calendar.vbs        SUN 06:00
call :register_vbs_weekly "TrendMaster TV Alert Renewer"      renew_expiring_alerts_hidden.vbs SUN 07:00
call :register_vbs_weekly "TrendMaster EA Parity Nightly"     hidden_ea_parity_nightly.vbs     MON 02:30

REM Health Watchdog — pythonw direct (already silent, re-applied)
echo.
echo === Health Watchdog (pythonw direct, every 1 min) ===
schtasks /Delete /TN "TrendMaster Health Watchdog" /F >nul 2>&1
schtasks /Create /TN "TrendMaster Health Watchdog" ^
  /TR "\"%PYW%\" \"%TOOLS%\health_watchdog.py\" --once" ^
  /SC MINUTE /MO 1 /RL LIMITED /F >>"%OUTLOG%" 2>&1
echo  [DONE] Health Watchdog re-applied

REM Master Autostart — pythonw direct, ONLOGON
echo.
echo === Master Autostart (pythonw direct, ONLOGON) ===
schtasks /Delete /TN "TrendMaster Master Autostart" /F >nul 2>&1
schtasks /Create /TN "TrendMaster Master Autostart" ^
  /TR "\"%PYW%\" \"%TOOLS%\master_autostart.py\"" ^
  /SC ONLOGON /F >>"%OUTLOG%" 2>&1
echo  [DONE] Master Autostart re-applied

REM Hourly Telegram snapshot — pythonw direct
echo.
echo === Hourly Telegram Snapshot (pythonw direct, hourly) ===
schtasks /Delete /TN "TrendMaster Hourly Snapshot" /F >nul 2>&1
schtasks /Create /TN "TrendMaster Hourly Snapshot" ^
  /TR "\"%PYW%\" \"%TOOLS%\hourly_telegram_snapshot.py\"" ^
  /SC HOURLY /F >>"%OUTLOG%" 2>&1
echo  [DONE] Hourly Snapshot re-applied

REM Daily Telegram summary — pythonw direct
echo.
echo === Daily Telegram Summary (pythonw direct, 23:00) ===
schtasks /Delete /TN "TrendMaster Daily Summary" /F >nul 2>&1
schtasks /Create /TN "TrendMaster Daily Summary" ^
  /TR "\"%PYW%\" \"%TOOLS%\daily_telegram_summary.py\"" ^
  /SC DAILY /ST 23:00 /F >>"%OUTLOG%" 2>&1
echo  [DONE] Daily Summary re-applied

REM OpenClaw Gateway — wscript hidden_gateway.vbs (ONLOGON)
echo.
echo === OpenClaw Gateway (wscript hidden_gateway.vbs, ONLOGON) ===
set "OC_VBS=C:\Users\Ratanshila\.openclaw\hidden_gateway.vbs"
if exist "%OC_VBS%" (
    schtasks /Delete /TN "OpenClaw Gateway" /F >nul 2>&1
    schtasks /Create /TN "OpenClaw Gateway" /TR "wscript.exe \"%OC_VBS%\"" /SC ONLOGON /F >>"%OUTLOG%" 2>&1
    echo  [DONE] OpenClaw Gateway re-applied
) else (
    echo  [SKIP] %OC_VBS% missing
)

REM ─────────────────────────────────────────────────────────────────
REM  KILL any currently-flashing children
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  Killing existing visible cmd / wrapper processes
echo ============================================================
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*run_tv_webhook_watchdog*' -or $_.CommandLine -like '*junction_guard*' -or $_.CommandLine -like '*schtasks_audit*' } | ForEach-Object { Write-Host '  killing PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

REM ─────────────────────────────────────────────────────────────────
REM  VERIFY — print Task To Run for every task we just touched
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  VERIFY — every task should now use wscript or pythonw (no cmd, no python.exe)
echo ============================================================
echo.
for %%T in (
    "TrendMaster TV Webhook Watchdog"
    "TrendMaster Junction Guard"
    "TrendMaster Schtasks Audit"
    "TrendMaster Process Watchdog"
    "TrendMaster Health Watchdog"
    "TrendMaster Master Autostart"
    "TrendMaster Brain Watchpet"
    "TrendMaster Pytest Health Check"
    "TrendMaster Signal Outcome Collector"
    "TrendMaster Watch-Pets"
    "TrendMaster Brain Liveness"
    "TrendMaster Alert Bridge"
    "TrendMaster Code Graph Rebuild"
    "TrendMaster Events Rotator"
    "TrendMaster Daily Maintenance"
    "TrendMaster Daily Summary"
    "TrendMaster Hourly Snapshot"
    "TrendMaster Zero Trades Watchdog"
    "OpenClaw Gateway"
) do (
    echo.
    echo --- %%T ---
    schtasks /Query /TN %%T /FO LIST 2>nul | findstr /C:"Task To Run" /C:"Status"
)

echo.
echo ============================================================
echo  DONE — all popups should stop within 5 minutes.
echo  If a popup STILL appears, identify it by reading its title bar
echo  and add it to this script.
echo ============================================================
echo.
echo Run log: %OUTLOG%
pause
goto :eof

REM ────────────────────────────────────────────────────────────────────
REM  Subroutines
REM ────────────────────────────────────────────────────────────────────
:register_vbs_min
set "TN=%~1"
set "VBSF=%~2"
set "MIN=%~3"
echo.
echo === %TN% (every %MIN% min) ===
if not exist "%TOOLS%\%VBSF%" (
    echo  [SKIP] %TOOLS%\%VBSF% missing
    goto :eof
)
schtasks /Delete /TN "%TN%" /F >nul 2>&1
schtasks /Create /TN "%TN%" /TR "wscript.exe \"%TOOLS%\%VBSF%\"" /SC MINUTE /MO %MIN% /RL LIMITED /F >>"%OUTLOG%" 2>&1
if errorlevel 1 (echo  [X] %TN% failed) else (echo  [DONE] %TN% re-applied)
goto :eof

:register_vbs_daily
set "TN=%~1"
set "VBSF=%~2"
set "TIME=%~3"
echo.
echo === %TN% (daily %TIME%) ===
if not exist "%TOOLS%\%VBSF%" (
    echo  [SKIP] %TOOLS%\%VBSF% missing
    goto :eof
)
schtasks /Delete /TN "%TN%" /F >nul 2>&1
schtasks /Create /TN "%TN%" /TR "wscript.exe \"%TOOLS%\%VBSF%\"" /SC DAILY /ST %TIME% /F >>"%OUTLOG%" 2>&1
if errorlevel 1 (echo  [X] %TN% failed) else (echo  [DONE] %TN% re-applied)
goto :eof

:register_vbs_weekly
set "TN=%~1"
set "VBSF=%~2"
set "DAY=%~3"
set "TIME=%~4"
echo.
echo === %TN% (weekly %DAY% %TIME%) ===
if not exist "%TOOLS%\%VBSF%" (
    echo  [SKIP] %TOOLS%\%VBSF% missing
    goto :eof
)
schtasks /Delete /TN "%TN%" /F >nul 2>&1
schtasks /Create /TN "%TN%" /TR "wscript.exe \"%TOOLS%\%VBSF%\"" /SC WEEKLY /D %DAY% /ST %TIME% /F >>"%OUTLOG%" 2>&1
if errorlevel 1 (echo  [X] %TN% failed) else (echo  [DONE] %TN% re-applied)
goto :eof
