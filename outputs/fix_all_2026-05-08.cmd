@echo off
REM ============================================================================
REM   fix_all_2026-05-08.cmd  —  Sumit's laptop-restart recovery
REM
REM   Three problems being fixed in one run:
REM     1. Trading project doesn't open properly after laptop reboot
REM     2. Terminal popups flash every minute (schtasks using visible cmd)
REM     3. Rocket Prime signals not firing (ngrok tunnel stuck)
REM
REM   The watchdog log shows ngrok.out is permission-denied since 10:29 today
REM   because a stale process holds a file handle. Master_autostart fired but
REM   reported PARTIAL because it can't bring ngrok up.
REM
REM   Strategy: surgical kill of all stale procs, release file locks, then
REM   relaunch the entire pipeline through the canonical entry points.
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo.
echo ============================================================
echo   PHASE 1/5  — Killing stale processes
echo ============================================================

REM Kill the brain first (so it can't write state mid-restart)
echo  - killing brain (trend_master_brain)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

REM Kill webhook receivers (we have 3 zombies per master_autostart.log)
echo  - killing tv_webhook_receiver
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

REM Kill executors (2 zombies)
echo  - killing python_signal_executor
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

REM Kill trailing stop managers (4 zombies)
echo  - killing trailing_stop_manager
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*trailing_stop_manager*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

REM Kill dashboard (zombies reported)
echo  - killing dashboard_server
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*dashboard_server*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

REM Kill ngrok (the file-locker)
echo  - killing ngrok.exe
taskkill /F /IM ngrok.exe 2>nul
taskkill /F /IM cloudflared.exe 2>nul

REM Clear singleton locks
echo  - clearing singleton locks
del /f /q logs\python_signal_executor.lock 2>nul
del /f /q logs\trailing_stop_manager.lock 2>nul
del /f /q logs\brain.lock 2>nul
del /f /q logs\tv_webhook_receiver.lock 2>nul

echo.
echo  - waiting 8 seconds for Windows to release file handles
ping 127.0.0.1 -n 9 >nul

echo.
echo ============================================================
echo   PHASE 2/5  — Truncating locked log files
echo ============================================================

REM Truncate the locked ngrok logs that started the cascade
type nul > logs\ngrok.out 2>nul
if errorlevel 1 (
    echo  [!] could not truncate ngrok.out — file still locked, retry...
    ping 127.0.0.1 -n 6 >nul
    type nul > logs\ngrok.out 2>nul
)
type nul > logs\ngrok.err 2>nul
type nul > logs\tv_webhook.bootstrap.out 2>nul
type nul > logs\tv_webhook.bootstrap.err 2>nul
echo  - ngrok.out / ngrok.err / tv_webhook.bootstrap.* truncated

REM Reset watchdog cooldowns so it can act immediately if needed
echo  - resetting watchdog cooldowns
.venv\Scripts\python.exe -c "import json, time; from pathlib import Path; p = Path('logs/watchdog_state.json'); s = json.loads(p.read_text()) if p.exists() else {}; [s.pop(k) for k in list(s.keys()) if k.startswith('last_action_')]; p.write_text(json.dumps(s, indent=2))"

echo.
echo ============================================================
echo   PHASE 3/5  — Restarting webhook + tunnel  (start_tv_webhook.cmd)
echo ============================================================
echo.
call start_tv_webhook.cmd
if errorlevel 1 (
    echo [X] start_tv_webhook.cmd reported failure — see logs\tv_webhook.bootstrap.err
    goto :phase4
)

:phase4
echo.
echo ============================================================
echo   PHASE 4/5  — Restarting brain  (start_brain_clean.cmd)
echo ============================================================
echo.
call start_brain_clean.cmd
if errorlevel 1 (
    echo [X] start_brain_clean.cmd reported failure — see logs\trend_master_brain.err
    goto :phase5
)

:phase5
echo.
echo ============================================================
echo   PHASE 5/5  — master_autostart  (executor + trailing + dashboard)
echo ============================================================
echo.
.venv\Scripts\python.exe tools\master_autostart.py

echo.
echo ============================================================
echo   VERIFY
echo ============================================================
echo.
echo  - waiting 12s for components to settle
ping 127.0.0.1 -n 13 >nul

echo  - watchdog cycle (forced, fresh)
.venv\Scripts\python.exe tools\health_watchdog.py --once
echo.
echo  - watchdog status report
.venv\Scripts\python.exe tools\health_watchdog.py --status
echo.

echo  - quick gate diagnostic
.venv\Scripts\python.exe tools\diagnose_zero_trades.py
echo.

echo  - public webhook health (TradingView reachability)
.venv\Scripts\python.exe -c "import urllib.request, ssl; req = urllib.request.Request('https://shadow-cosmos-unending.ngrok-free.dev/health', headers={'ngrok-skip-browser-warning': 'true'}); r = urllib.request.urlopen(req, timeout=10); print('  PUBLIC OK status=', r.status, 'body=', r.read().decode()[:200])" 2>nul
if errorlevel 1 (
    echo  [!] public /health still unreachable — TradingView signals will fail.
    echo      Possible causes: ngrok session conflict, ngrok-free reserved-domain
    echo      timeout, or your laptop has changed networks.
    echo      Run:  type logs\ngrok.out  ^|  more
)
echo.
echo ============================================================
echo   DONE — recovery script complete.
echo ============================================================
echo.
echo  Next: hit a Rocket Prime alert manually from TradingView, then
echo  watch logs\python_executor.log to confirm:
echo      type logs\python_executor.log ^| findstr /C:"SAFEGUARD BLOCK" /C:"placed order" /C:"skip"
echo.
endlocal
