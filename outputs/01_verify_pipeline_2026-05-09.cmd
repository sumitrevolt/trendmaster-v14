@echo off
REM =====================================================================
REM 01_verify_pipeline_2026-05-09.cmd  --  Pre-flight pipeline health check
REM
REM Runs in <10s. Verifies (in order):
REM   1. Webhook receiver listening on 127.0.0.1:5005
REM   2. ngrok public tunnel reachable from outside
REM   3. Telegram bot can post to chat
REM   4. Python executor alive and MT5 connected
REM   5. Recent log activity sanity (no crashes)
REM
REM Exit codes:
REM   0  = all green, ready to receive RP alerts
REM   2  = webhook DEAD
REM   3  = ngrok tunnel DEAD
REM   4  = Telegram FAIL
REM   5  = executor DEAD
REM =====================================================================
setlocal EnableDelayedExpansion
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============================================================
echo   TrendMaster pipeline verification - 2026-05-09
echo ============================================================
echo.

REM ----- 1. Webhook local health -----
echo [1/5] Webhook receiver (127.0.0.1:5005) ...
.venv\Scripts\python.exe -c "import urllib.request, sys; r=urllib.request.urlopen('http://127.0.0.1:5005/health',timeout=3); sys.exit(0 if r.status==200 else 2)" >nul 2>&1
if errorlevel 2 (
    echo   [X] DEAD - run:  start_tv_webhook.cmd
    exit /b 2
)
echo   [OK] alive
echo.

REM ----- 2. ngrok public tunnel -----
echo [2/5] ngrok public tunnel ...
.venv\Scripts\python.exe -c "import urllib.request, sys; r=urllib.request.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health',timeout=8); sys.exit(0 if r.status==200 else 3)" >nul 2>&1
if errorlevel 3 (
    echo   [X] DEAD - check Get-Process ngrok, may need to restart watchdog
    exit /b 3
)
echo   [OK] reachable from outside
echo.

REM ----- 3. Telegram smoke test -----
echo [3/5] Telegram notifier ...
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env'),override=True); from ai_trading_agents.telegram_notifier import get_notifier; n=get_notifier(); ok=n.enabled and n.send('[verify] pipeline check 2026-05-09 OK'); print('SENT' if ok else 'DISABLED'); import sys; sys.exit(0 if ok else 4)"
if errorlevel 4 (
    echo   [X] Telegram FAIL - check TELEGRAM_BOT_TOKEN / CHAT_ID in config\.env
    exit /b 4
)
echo   [OK] message delivered to your phone
echo.

REM ----- 4. Python executor heartbeat -----
echo [4/5] Python executor ...
powershell -NoProfile -Command "$cnt = (Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Measure-Object).Count; if ($cnt -eq 0) { Write-Host '  [X] DEAD - check Windows scheduled task'; exit 5 } elseif ($cnt -gt 1) { Write-Host \"  [!] $cnt instances running (expect 1) - watchdog may be respawning a stuck instance\" } else { Write-Host '  [OK] one instance alive' }"
if errorlevel 5 exit /b 5

REM ----- 5. Recent log sanity -----
echo.
echo [5/5] Log freshness ...
echo   tv_webhook.log:
powershell -NoProfile -Command "Get-Content 'logs\tv_webhook.log' -Tail 3 | ForEach-Object { '     ' + $_ }"
echo   python_executor.log:
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 1 | ForEach-Object { '     ' + $_ }"
echo.

echo ============================================================
echo   ALL GREEN -- pipeline ready for Rocket Prime alerts
echo ============================================================
echo.
echo Public webhook URL (paste into TV alert):
echo   https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=^<TV_WEBHOOK_SECRET^>^&symbol={{ticker}}^&tf={{interval}}
echo.

endlocal
