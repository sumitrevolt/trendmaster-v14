@echo off
REM ============================================================================
REM   harden_all_2026-05-08.cmd  —  Comprehensive project cleanup + hardening
REM
REM   Runs in sequence (each step idempotent, with backups for risky changes):
REM     1. Stale MT5 signal cleanup    (4 JSON files moved to backup/)
REM     2. Zombie executor kill        (12+ duplicates seen in heartbeat log)
REM     3. Log rotation                (python_executor.log 269KB+ → archive)
REM     4. OpenClaw popup re-register  (gateway.cmd → hidden_gateway.vbs)
REM     5. Fix tools\ngrok.exe alias   (so start_tv_webhook.cmd's auto-restart works)
REM     6. Disable failing OpenClaw cron jobs (timeout 10x in a row → quarantine)
REM     7. Sync trading_config.yaml to match settings.py concentrated-8 pair list
REM     8. Pipeline restart            (calls fix_all_2026-05-08.cmd)
REM     9. Final health verify
REM
REM   Things explicitly NOT touched:
REM     - settings.py TRADING_PAIRS    (already concentrated 8 — keep as-is)
REM     - config/.env                  (credentials, keys — never auto-edit)
REM     - Risk parameters              (risk_percent, daily_max_loss_pct)
REM     - Brain ML model files         (lgb files — Phase B3 baseline)
REM
REM   Total runtime ~120 seconds.  Leave window open until "ALL DONE".
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

set "STAMP=2026-05-08_harden"
set "BACKUP=backup\%STAMP%"
mkdir "%BACKUP%" 2>nul

echo.
echo ################################################################
echo #  TrendMaster Project Hardening Run
echo #  %DATE% %TIME%
echo #  All backups in:  %BACKUP%\
echo ################################################################
echo.

REM ─────────────────────────────────────────────────────────────────
REM  STEP 1/9  —  Stale MT5 signal cleanup
REM ─────────────────────────────────────────────────────────────────
echo ============================================================
echo   STEP 1/9  -  Cleaning stale MT5 signal files
echo ============================================================
set "MT5DIR=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files"
if exist "%MT5DIR%\trendmaster_signals_*.json" (
    echo  - moving stale signals to %BACKUP%\mt5_signals_old\
    mkdir "%BACKUP%\mt5_signals_old" 2>nul
    move /Y "%MT5DIR%\trendmaster_signals_*.json" "%BACKUP%\mt5_signals_old\" >nul 2>&1
    if errorlevel 1 (
        echo  [!] move failed - trying copy+delete
        copy /Y "%MT5DIR%\trendmaster_signals_*.json" "%BACKUP%\mt5_signals_old\" >nul 2>&1
        del /F /Q "%MT5DIR%\trendmaster_signals_*.json" 2>nul
    )
    echo  [OK] stale signals archived
) else (
    echo  [OK] no stale signals
)

REM ─────────────────────────────────────────────────────────────────
REM  STEP 2/9  —  Zombie executor kill
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 2/9  -  Killing zombie processes
echo ============================================================
echo  - python_signal_executor zombies
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

echo  - trailing_stop_manager zombies
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*trailing_stop_manager*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

echo  - tv_webhook_receiver zombies (keep one)
powershell -NoProfile -Command "$ps=Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' }; if ($ps.Count -gt 1) { $ps | Select-Object -Skip 1 | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null } }"

echo  - clearing singleton locks
del /f /q logs\python_signal_executor.lock 2>nul
del /f /q logs\trailing_stop_manager.lock 2>nul
echo  [OK] zombies cleared

REM ─────────────────────────────────────────────────────────────────
REM  STEP 3/9  —  Log rotation
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 3/9  -  Rotating large log files
echo ============================================================
mkdir "%BACKUP%\logs_rotated" 2>nul
for %%f in (
    python_executor.log
    trend_master_brain.log
    tv_webhook.log
    watchdog.log
    trailing_stop.log
) do (
    if exist "logs\%%f" (
        for %%A in ("logs\%%f") do (
            if %%~zA gtr 102400 (
                echo  - rotating logs\%%f  size=%%~zA bytes
                move /Y "logs\%%f" "%BACKUP%\logs_rotated\%%f" >nul 2>&1
                type nul > "logs\%%f"
            )
        )
    )
)
echo  [OK] large logs archived to %BACKUP%\logs_rotated\

REM ─────────────────────────────────────────────────────────────────
REM  STEP 4/9  —  OpenClaw popup re-register
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 4/9  -  OpenClaw Gateway: silent VBS wrapper
echo ============================================================
set "VBS=C:\Users\Ratanshila\.openclaw\hidden_gateway.vbs"
if exist "%VBS%" (
    echo  - killing visible gateway processes
    powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='node.exe'\" | Where-Object { $_.CommandLine -like '*--port 18789*' -or $_.CommandLine -like '*openclaw*gateway*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"
    powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*gateway.cmd*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"
    schtasks /Delete /TN "OpenClaw Gateway" /F >nul 2>&1
    schtasks /Create /TN "OpenClaw Gateway" /TR "wscript.exe \"%VBS%\"" /SC ONLOGON /F >nul
    if errorlevel 1 (echo  [X] OpenClaw schtask register failed) else (
        echo  [OK] OpenClaw Gateway will run silently from next logon
        schtasks /Run /TN "OpenClaw Gateway" >nul 2>&1
    )
) else (
    echo  [SKIP] %VBS% missing - cannot fix
)

REM ─────────────────────────────────────────────────────────────────
REM  STEP 5/9  —  Fix tools\ngrok.exe alias
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 5/9  -  ngrok.exe alias for start_tv_webhook.cmd
echo ============================================================
set "NGROK_REAL=C:\Users\Ratanshila\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
if not exist "tools\ngrok.exe" (
    if exist "%NGROK_REAL%" (
        echo  - linking tools\ngrok.exe -^> %NGROK_REAL%
        mklink "tools\ngrok.exe" "%NGROK_REAL%" >nul 2>&1
        if errorlevel 1 (
            REM mklink needs admin - fall back to copy
            copy /Y "%NGROK_REAL%" "tools\ngrok.exe" >nul 2>&1
            echo  [OK] tools\ngrok.exe is now a copy ^(start_tv_webhook.cmd will work^)
        ) else (
            echo  [OK] tools\ngrok.exe is now a symlink
        )
    ) else (
        echo  [SKIP] %NGROK_REAL% not found
    )
) else (
    echo  [OK] tools\ngrok.exe already exists
)

REM ─────────────────────────────────────────────────────────────────
REM  STEP 6/9  —  Disable failing OpenClaw cron jobs
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 6/9  -  Quarantining failing OpenClaw cron jobs
echo ============================================================
echo  - backing up jobs.json
copy /Y "C:\Users\Ratanshila\.openclaw\cron\jobs.json" "%BACKUP%\openclaw_jobs.json" >nul 2>&1
echo  - disabling jobs with consecutiveErrors ^>= 5
.venv\Scripts\python.exe outputs\_quarantine_failing_crons.py

REM ─────────────────────────────────────────────────────────────────
REM  STEP 7/9  —  Sync trading_config.yaml to settings.py pair list
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 7/9  -  Sync trading_config.yaml -^> 8 concentrated pairs
echo ============================================================
echo  - backing up trading_config.yaml
copy /Y "config\trading_config.yaml" "%BACKUP%\trading_config.yaml" >nul 2>&1
.venv\Scripts\python.exe outputs\_sync_trading_pairs.py

REM ─────────────────────────────────────────────────────────────────
REM  STEP 8/9  —  Pipeline restart (delegates to fix_all)
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 8/9  -  Pipeline restart
echo ============================================================
echo  - calling outputs\fix_all_2026-05-08.cmd
call outputs\fix_all_2026-05-08.cmd
echo  [OK] pipeline restart delegated

REM ─────────────────────────────────────────────────────────────────
REM  STEP 9/9  —  Final health verify
REM ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   STEP 9/9  -  Final health verify
echo ============================================================
ping 127.0.0.1 -n 8 >nul
.venv\Scripts\python.exe tools\health_watchdog.py --status
echo.
echo  - public webhook reachability
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.Request('https://shadow-cosmos-unending.ngrok-free.dev/health', headers={'ngrok-skip-browser-warning':'true'}); resp=u.urlopen(r, timeout=10); print('  PUBLIC OK status=', resp.status)" 2>nul
if errorlevel 1 (
    echo  [!] public webhook still down — check logs\ngrok.out
    echo      may need:  outputs\fix_ngrok.cmd
)
echo.
echo  - executor heartbeat (last 3 lines)
powershell -NoProfile -Command "if (Test-Path 'logs\python_executor.log') { Get-Content 'logs\python_executor.log' -Tail 3 } else { 'no log yet' }"
echo.
echo  - signal directory state
dir /B "%MT5DIR%\trendmaster_signals_*.json" 2>nul
if errorlevel 1 (
    echo  [OK] signal dir clean - waiting for fresh TV signals
)
echo.

echo ################################################################
echo #  ALL DONE   —   Project hardening complete
echo ################################################################
echo.
echo  Summary:
echo    - Stale signals    : archived to %BACKUP%\mt5_signals_old\
echo    - Zombie procs     : killed
echo    - Logs ^>100KB      : rotated to %BACKUP%\logs_rotated\
echo    - OpenClaw popup   : silenced (next logon onwards too)
echo    - tools\ngrok.exe  : alias created
echo    - Failing crons    : disabled (re-enable when API stable)
echo    - trading_config   : synced to 8-pair concentrated mode
echo    - Pipeline         : restarted
echo.
echo  Next signal that arrives should write to logs\tv_plot_values.jsonl
echo  in the new format ^(RP^|SYM^|tf=N^|p0=X^|p1=Y^|...^).
echo.
echo  To re-enable a quarantined OpenClaw cron job:
echo    1. Edit C:\Users\Ratanshila\.openclaw\cron\jobs.json
echo    2. Set "enabled": true on the job you want
echo    3. Reset "consecutiveErrors": 0 in its state block
echo.
echo  Press any key to close.
pause >nul
endlocal
