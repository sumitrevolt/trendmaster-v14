@echo off
REM ───────────────────────────────────────────────────────────────────
REM   TradingView webhook receiver launcher
REM   Added 2026-05-01 — starts ai_trading_agents.tv_webhook_receiver
REM   detached, logs to logs\tv_webhook.log + logs\tv_webhook.err
REM ───────────────────────────────────────────────────────────────────

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Pre-flight: TV_WEBHOOK_SECRET must be set in config\.env
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os; import sys; sys.exit(0 if os.getenv('TV_WEBHOOK_SECRET','').strip() else 2)"
if errorlevel 2 (
    echo [X] PRE-FLIGHT FAIL: TV_WEBHOOK_SECRET is not set in config\.env
    echo     Add a random 32+ char string, e.g.:
    echo         TV_WEBHOOK_SECRET=^<paste output of: python -c "import secrets; print(secrets.token_hex(24))"^>
    exit /b 2
)

REM Pre-flight: import works (catches junction breakage, missing deps)
.venv\Scripts\python.exe -c "import ai_trading_agents.tv_webhook_receiver" >nul 2>&1
if errorlevel 1 (
    echo [X] PRE-FLIGHT FAIL: ai_trading_agents.tv_webhook_receiver failed to import.
    echo     Test manually: .venv\Scripts\python.exe -c "import ai_trading_agents.tv_webhook_receiver"
    exit /b 3
)
echo [OK] PRE-FLIGHT: webhook receiver imports cleanly.

REM Kill any prior receiver
echo === killing any prior tv_webhook process ===
for /f "tokens=2" %%a in ('tasklist /v /fi "imagename eq python.exe" ^| findstr /i "TV_Webhook"') do taskkill /F /PID %%a 2>nul

REM Truncate log files for a clean run
echo === truncating tv_webhook logs ===
type nul > logs\tv_webhook.log
type nul > logs\tv_webhook.err

echo === starting TV webhook receiver detached ===
start "TV_Webhook - LIVE" /MIN cmd /c "title TV_Webhook - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u -m ai_trading_agents.tv_webhook_receiver 1>> logs\tv_webhook.log 2>> logs\tv_webhook.err"

echo === wait 3s for boot ===
ping 127.0.0.1 -n 4 >nul

REM Boot crash check — if the .err file has a Traceback, fail loudly
.venv\Scripts\python.exe -c "import sys, pathlib; p = pathlib.Path(r'logs\tv_webhook.err'); txt = p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''; sys.exit(2 if 'Traceback' in txt else 0)"
if errorlevel 2 (
    echo [X] BOOT CRASH: logs\tv_webhook.err contains a Traceback.
    echo     Tail of error log:
    powershell -NoProfile -Command "Get-Content -Path 'logs\tv_webhook.err' -Tail 25"
    exit /b 5
)

echo === health check ===
.venv\Scripts\python.exe -c "import urllib.request, os; from dotenv import load_dotenv; load_dotenv('config/.env'); host=os.getenv('TV_WEBHOOK_HOST','127.0.0.1'); port=os.getenv('TV_WEBHOOK_PORT','5005'); r=urllib.request.urlopen(f'http://{host}:{port}/health', timeout=3); print('[OK] health:', r.read().decode())"
if errorlevel 1 (
    echo [X] HEALTH CHECK FAIL: receiver not responding on /health
    powershell -NoProfile -Command "Get-Content -Path 'logs\tv_webhook.log' -Tail 25"
    exit /b 6
)

echo === DONE — webhook live. See docs\TV_SIGNAL_SETUP.md for tunnel + TV alert setup ===
