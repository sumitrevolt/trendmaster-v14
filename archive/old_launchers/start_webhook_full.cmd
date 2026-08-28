@echo off
REM ───────────────────────────────────────────────────────────────────
REM   One-click TradingView webhook launcher
REM   Created 2026-05-01 — no ngrok signup needed
REM   What it does:
REM     1. Downloads cloudflared.exe if missing
REM     2. Starts the webhook receiver (port 5005, local)
REM     3. Starts a Cloudflare quick tunnel (free, no signup)
REM     4. Writes the public URL to logs\webhook_url.txt
REM ───────────────────────────────────────────────────────────────────

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Step 1: Ensure cloudflared.exe exists
if not exist "tools\cloudflared.exe" (
    echo [1/4] cloudflared.exe missing — downloading ^(~25 MB^)...
    if not exist "tools" mkdir tools
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'tools\cloudflared.exe' -UseBasicParsing"
    if not exist "tools\cloudflared.exe" (
        echo [X] Download failed. Check internet connection.
        pause
        exit /b 1
    )
    echo [OK] cloudflared.exe downloaded.
) else (
    echo [1/4] cloudflared.exe already present.
)

REM Step 2: Pre-flight + start webhook receiver detached
echo [2/4] Starting webhook receiver...
.venv\Scripts\python.exe -c "import ai_trading_agents.tv_webhook_receiver" >nul 2>&1
if errorlevel 1 (
    echo [X] PRE-FLIGHT FAIL: ai_trading_agents.tv_webhook_receiver does not import.
    pause
    exit /b 2
)

REM Kill any prior receiver
for /f "tokens=2" %%a in ('tasklist /v /fi "imagename eq python.exe" ^| findstr /i "TV_Webhook"') do taskkill /F /PID %%a 2>nul

REM Don't truncate tv_webhook.log — Python's FileHandler owns that.
REM Only truncate the cmd console capture files.
type nul > logs\tv_webhook_console.out
type nul > logs\tv_webhook.err

start "TV_Webhook - LIVE" /MIN cmd /c "title TV_Webhook - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u -m ai_trading_agents.tv_webhook_receiver 1>> logs\tv_webhook_console.out 2>> logs\tv_webhook.err"

ping 127.0.0.1 -n 4 >nul

REM Health check
.venv\Scripts\python.exe -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5005/health', timeout=3); print('[OK] receiver health:', r.read().decode())"
if errorlevel 1 (
    echo [X] Webhook receiver did not respond on /health.
    powershell -NoProfile -Command "Get-Content -Path 'logs\tv_webhook.err' -Tail 20"
    pause
    exit /b 3
)

REM Step 3: Kill any prior cloudflared
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq cloudflared.exe" /fo csv ^| findstr /i "cloudflared"') do taskkill /F /PID %%a 2>nul

REM Step 4: Start cloudflared quick tunnel (logs URL to file)
echo [3/4] Starting Cloudflare quick tunnel...
type nul > logs\cloudflared.log
type nul > logs\webhook_url.txt
start "Cloudflared - LIVE" /MIN cmd /c "title Cloudflared - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && tools\cloudflared.exe tunnel --url http://localhost:5005 --logfile logs\cloudflared.log 1>> logs\cloudflared.log 2>> logs\cloudflared.log"

REM Wait for cloudflared to print the URL (up to 30s)
echo [4/4] Waiting for tunnel URL ^(up to 30s^)...
set TRIES=0
:wait_url
ping 127.0.0.1 -n 3 >nul
set /a TRIES=%TRIES% + 1
.venv\Scripts\python.exe -c "import re, pathlib; t=pathlib.Path('logs/cloudflared.log').read_text(errors='replace'); m=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', t); print(m.group(0)) if m else exit(1)" > logs\webhook_url.txt 2>nul
if exist logs\webhook_url.txt (
    for /f "delims=" %%u in (logs\webhook_url.txt) do set URL=%%u
)
if "%URL%"=="" (
    if %TRIES% LSS 12 goto wait_url
    echo [X] Tunnel URL did not appear in 30s. Check logs\cloudflared.log
    powershell -NoProfile -Command "Get-Content -Path 'logs\cloudflared.log' -Tail 40"
    pause
    exit /b 4
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo   PUBLIC WEBHOOK URL (paste this in TradingView alert):
echo.
echo   %URL%/tv-signal
echo.
echo   URL also saved to: logs\webhook_url.txt
echo ═══════════════════════════════════════════════════════════════
echo.
echo Both processes are running in minimized windows:
echo   - "TV_Webhook - LIVE"   (receiver on port 5005)
echo   - "Cloudflared - LIVE"  (public tunnel)
echo.
echo To stop: close both minimized windows OR run STOP_WEBHOOK.cmd
echo.
pause
