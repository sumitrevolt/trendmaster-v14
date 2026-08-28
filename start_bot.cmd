@echo off
REM ─── TrendMaster TV-bot launcher (single click) ─────────────────────
REM Starts BOTH:
REM   1. webhook receiver  (port 5005, all 35 pairs)
REM   2. cloudflared quick tunnel  (public HTTPS URL, no signup)
REM
REM Reads config from config\.env, prints final webhook URL,
REM stays alive so a Ctrl+C cleanly stops both processes.

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============================================================
echo   TrendMaster TV-bot — start_bot
echo ============================================================
echo.

REM Pre-flight: secret + cloudflared.exe present
if not exist "tools\cloudflared.exe" (
    echo [.] cloudflared.exe missing — downloading once ^(~25 MB^)...
    if not exist "tools" mkdir tools
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'tools\cloudflared.exe' -UseBasicParsing" || (echo [X] download failed & pause & exit /b 1)
    echo [+] cloudflared.exe ready.
)

.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os, sys; sys.exit(0 if os.getenv('TV_WEBHOOK_SECRET','').strip() else 1)" || (echo [X] TV_WEBHOOK_SECRET not set in config\.env & pause & exit /b 2)

echo [.] killing any prior instance...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"

REM Truncate logs (Python's FileHandler will recreate)
del /f /q logs\tv_webhook.log 2>nul
del /f /q logs\cloudflared.err 2>nul

echo [.] starting webhook receiver...
REM Redirect stdout/stderr to files — python crashes on broken-pipe writes
REM if the launching console exits and stdout/stderr are unbound. The cmd
REM wrapper holds the redirection alive for the lifetime of the python child.
start "TrendMaster_Webhook" /MIN cmd /c ".venv\Scripts\python.exe -u -m ai_trading_agents.tv_webhook_receiver 1>>logs\tv_webhook_console.out 2>>logs\tv_webhook_console.err"

REM Wait until port 5005 is listening (up to 15 s)
echo [.] waiting for receiver to bind...
set /a TRIES=0
:wait_recv
ping 127.0.0.1 -n 2 >nul
.venv\Scripts\python.exe -c "import urllib.request, sys; r=urllib.request.urlopen('http://127.0.0.1:5005/health', timeout=2); sys.exit(0 if r.status==200 else 1)" >nul 2>&1 && goto recv_ok
set /a TRIES=%TRIES% + 1
if %TRIES% LSS 15 goto wait_recv
echo [X] receiver did not bind within 15s. Check logs\tv_webhook.log
pause
exit /b 3
:recv_ok
echo [+] receiver alive on 127.0.0.1:5005

echo [.] starting Cloudflare quick tunnel...
start "TrendMaster_Tunnel" /MIN cmd /c "tools\cloudflared.exe tunnel --url http://localhost:5005 1>> logs\cloudflared.err 2>&1"

REM Wait for tunnel URL to appear in cloudflared.err (up to 30 s)
echo [.] waiting for tunnel URL...
set /a TRIES=0
:wait_url
ping 127.0.0.1 -n 3 >nul
.venv\Scripts\python.exe -c "import re, pathlib; t=pathlib.Path('logs/cloudflared.err').read_text(errors='replace'); m=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', t); print(m.group(0)) if m else exit(1)" > logs\webhook_url_raw.txt 2>nul && goto url_ok
set /a TRIES=%TRIES% + 1
if %TRIES% LSS 12 goto wait_url
echo [X] Tunnel URL did not appear in 30s. Check logs\cloudflared.err
pause
exit /b 4
:url_ok
for /f "delims=" %%u in (logs\webhook_url_raw.txt) do set BASE_URL=%%u
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); s=os.getenv('TV_WEBHOOK_SECRET',''); print(f'%BASE_URL%/tv-signal?secret={s}&symbol={{{{ticker}}}}')" > logs\webhook_url.txt
for /f "delims=" %%u in (logs\webhook_url.txt) do set FULL_URL=%%u

echo.
echo ============================================================
echo   BOT IS LIVE. Both windows minimized in taskbar:
echo     TrendMaster_Webhook  (Python receiver)
echo     TrendMaster_Tunnel   (Cloudflare)
echo.
echo   PASTE THIS URL into TradingView alert -^> Webhook URL
echo   (one URL handles ALL 35 pairs via {{ticker}} substitution)
echo.
echo   %FULL_URL%
echo.
echo   URL also saved to: logs\webhook_url.txt
echo ============================================================
echo.
echo To check status:  status.cmd
echo To stop the bot:  stop_bot.cmd
echo.
pause
