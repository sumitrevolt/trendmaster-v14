@echo off
REM ============================================================================
REM remove_openclaw_2026-05-09.cmd  --  Run as Administrator (one click)
REM
REM Full removal of OpenClaw. Trading pipeline is independent and unaffected.
REM
REM What stays untouched:
REM   - All TrendMaster schtasks (29 silent ones)
REM   - tools/python_signal_executor.py (the actual trade dispatcher)
REM   - ai_trading_agents/ (the brain + webhook receiver)
REM   - config/.env, MT5, ngrok tunnel
REM
REM What this removes:
REM   - "OpenClaw Gateway" schtask
REM   - "OpenClaw Watchdog" schtask
REM   - Startup folder LNK + VBS for OpenClaw
REM   - Optionally: ~/.openclaw directory (commented out by default - your call)
REM   - Optionally: C:\oc\node_modules\openclaw (commented out)
REM
REM Backups: nothing destructive happens to ~/.openclaw or C:\oc.
REM Anything you uncomment that deletes a directory: do at your own risk.
REM ============================================================================

echo.
echo === Removing OpenClaw scheduled tasks ===
schtasks /Delete /TN "OpenClaw Gateway"  /F
schtasks /Delete /TN "OpenClaw Watchdog" /F

echo.
echo === Removing OpenClaw startup-folder entries ===
del /F "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Boot_OpenClaw_Trading.lnk" 2>nul
del /F "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\OpenClaw Gateway.vbs"      2>nul

echo.
echo === Verifying removal ===
schtasks /Query /TN "OpenClaw Gateway"  >nul 2>&1 && echo [WARN] OpenClaw Gateway still present  || echo [OK] OpenClaw Gateway gone
schtasks /Query /TN "OpenClaw Watchdog" >nul 2>&1 && echo [WARN] OpenClaw Watchdog still present || echo [OK] OpenClaw Watchdog gone

echo.
echo === OPTIONAL: data directories (NOT deleted by default) ===
echo.
echo If you also want to delete the OpenClaw config + node modules,
echo uncomment the lines below. They're left alone in case you ever
echo want to revive OpenClaw later.
echo.
REM rmdir /S /Q "C:\Users\Ratanshila\.openclaw"
REM rmdir /S /Q "C:\oc"

echo.
echo ============================================================
echo   DONE -- OpenClaw fully removed from active surfaces
echo ============================================================
echo.
echo Trading pipeline status (should be unaffected):
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5005/health' -UseBasicParsing -TimeoutSec 3; Write-Host '  Webhook:  ALIVE' -ForegroundColor Green } catch { Write-Host '  Webhook:  DEAD - run start_tv_webhook.cmd' -ForegroundColor Red }; $cnt = (Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object {$_.CommandLine -like '*python_signal_executor*'} | Measure-Object).Count; if ($cnt -gt 0) { Write-Host \"  Executor: ALIVE ($cnt instances)\" -ForegroundColor Green } else { Write-Host '  Executor: DEAD - check TrendMaster Health Watchdog schtask' -ForegroundColor Red }"
echo.
pause
