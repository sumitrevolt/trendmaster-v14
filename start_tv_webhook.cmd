@echo off
setlocal EnableDelayedExpansion
REM ───────────────────────────────────────────────────────────────────────────
REM   TradingView webhook receiver + tunnel launcher
REM   Brings up:
REM     1. ai_trading_agents.tv_webhook_receiver  on 127.0.0.1:5005
REM     2. A tunnel exposing it to the public internet
REM
REM   Tunnel mode is read from config\.env::TUNNEL_MODE:
REM     quick  (default)  — cloudflared --url http://localhost:5005
REM                          (URL rotates on every restart — breaks TV alerts!)
REM     named             — cloudflared --config config\cloudflared.yml run
REM                          (stable URL, requires one-time setup —
REM                           see docs\STABLE_TUNNEL_SETUP.md Path A)
REM     ngrok             — ngrok http 5005 --domain=$NGROK_DOMAIN
REM                          (stable URL, requires ngrok paid plan —
REM                           see docs\STABLE_TUNNEL_SETUP.md Path B)
REM     none              — receiver only, no tunnel
REM
REM   Logs: logs\tv_webhook.log/.err  +  logs\cloudflared.out/.err  (or ngrok.err)
REM ───────────────────────────────────────────────────────────────────────────

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM ── Pre-flight 1: TV_WEBHOOK_SECRET set ──
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os, sys; sys.exit(0 if os.getenv('TV_WEBHOOK_SECRET','').strip() else 2)"
if errorlevel 2 (
    echo [X] PRE-FLIGHT FAIL: TV_WEBHOOK_SECRET is not set in config\.env
    echo     Generate one with:  python -c "import secrets; print(secrets.token_hex(24))"
    exit /b 2
)

REM ── Pre-flight 2: webhook receiver imports cleanly ──
.venv\Scripts\python.exe -c "import ai_trading_agents.tv_webhook_receiver" >nul 2>&1
if errorlevel 1 (
    echo [X] PRE-FLIGHT FAIL: ai_trading_agents.tv_webhook_receiver failed to import.
    exit /b 3
)

REM ── Read TUNNEL_MODE from .env via a tiny python helper ──
for /f "delims=" %%m in ('.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os; print((os.getenv('TUNNEL_MODE') or 'quick').strip().lower())"') do set "TUNNEL_MODE=%%m"
echo [OK] PRE-FLIGHT: webhook OK. TUNNEL_MODE=%TUNNEL_MODE%

REM ── Pre-flight 3: tunnel binary present (mode-dependent) ──
if "%TUNNEL_MODE%"=="quick"  if not exist "tools\cloudflared.exe" (
    echo [X] tools\cloudflared.exe missing for quick tunnel
    exit /b 4
)
if "%TUNNEL_MODE%"=="named" if not exist "tools\cloudflared.exe" (
    echo [X] tools\cloudflared.exe missing for named tunnel
    exit /b 4
)
if "%TUNNEL_MODE%"=="named" if not exist "config\cloudflared.yml" (
    echo [X] config\cloudflared.yml missing for named tunnel mode.
    echo     See docs\STABLE_TUNNEL_SETUP.md Path A for one-time setup.
    exit /b 4
)
if "%TUNNEL_MODE%"=="ngrok" (
    where ngrok >nul 2>&1
    if errorlevel 1 if not exist "tools\ngrok.exe" (
        echo [X] ngrok not found. Install: winget install ngrok.ngrok
        echo     Or place ngrok.exe in tools\
        exit /b 4
    )
)
echo.

REM ── Kill any prior receiver / tunnel processes ──
REM   Use Get-CimInstance to match by command-line (window-title matching is
REM   unreliable on Windows Terminal). NEVER kills brain (different module).
echo === killing any prior tv_webhook + tunnel processes ===
for /f "tokens=*" %%p in ('powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter ('name = ''python.exe''') | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { $_.ProcessId }"') do taskkill /F /PID %%p 2>nul
taskkill /F /IM cloudflared.exe 2>nul
taskkill /F /IM ngrok.exe 2>nul
REM Give Windows a moment to release file handles before we touch the log files
ping 127.0.0.1 -n 3 >nul

REM ── Truncate logs ──
REM   IMPORTANT: cmd redirects (1>> 2>>) MUST go to different files than the
REM   ones python's logging.FileHandler opens. Otherwise Windows races the
REM   two handles and python gets PermissionError on tv_webhook.log.
REM   Python owns tv_webhook.log; cmd captures any leaked stdout/stderr in
REM   tv_webhook.bootstrap.{out,err}.
echo === truncating webhook + tunnel logs ===
del /f /q logs\tv_webhook.log logs\tv_webhook.err 2>nul
type nul > logs\tv_webhook.bootstrap.out
type nul > logs\tv_webhook.bootstrap.err
type nul > logs\cloudflared.out
type nul > logs\cloudflared.err
type nul > logs\ngrok.out
type nul > logs\ngrok.err

REM ── Start webhook receiver detached ──
echo === starting TV webhook receiver (port 5005) ===
REM 2026-05-13 popup fix: use wscript run_hidden.vbs instead of `start /MIN cmd /c`.
REM Even with /MIN, Win11 24H2 briefly flashes the cmd window which steals focus
REM while user is typing. run_hidden.vbs uses WindowStyle 0 (truly hidden).
wscript.exe "C:\Users\Ratanshila\Documents\autmated trading\tools\run_hidden.vbs" "cmd /c cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\pythonw.exe -u -m ai_trading_agents.tv_webhook_receiver 1>> logs\tv_webhook.bootstrap.out 2>> logs\tv_webhook.bootstrap.err"

ping 127.0.0.1 -n 4 >nul

REM ── Boot crash check ──
.venv\Scripts\python.exe -c "import sys, pathlib; p = pathlib.Path(r'logs\tv_webhook.bootstrap.err'); txt = p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''; sys.exit(2 if 'Traceback' in txt else 0)"
if errorlevel 2 (
    echo [X] BOOT CRASH: logs\tv_webhook.bootstrap.err contains a Traceback.
    powershell -NoProfile -Command "Get-Content -Path 'logs\tv_webhook.bootstrap.err' -Tail 25"
    exit /b 5
)

REM ── Local health check ──
echo === local health check ===
.venv\Scripts\python.exe -c "import urllib.request, os; from dotenv import load_dotenv; load_dotenv('config/.env'); host=os.getenv('TV_WEBHOOK_HOST','127.0.0.1'); port=os.getenv('TV_WEBHOOK_PORT','5005'); r=urllib.request.urlopen(f'http://{host}:{port}/health', timeout=3); print('[OK] /health:', r.read().decode())"
if errorlevel 1 (
    echo [X] LOCAL HEALTH FAIL: receiver not responding
    powershell -NoProfile -Command "Get-Content -Path 'logs\tv_webhook.log' -Tail 25"
    exit /b 6
)
echo.

REM ── Start tunnel based on mode ──
if "%TUNNEL_MODE%"=="none" (
    echo === DONE — receiver up, no tunnel ^(TUNNEL_MODE=none^) ===
    echo   Local URL: http://127.0.0.1:5005/tv-signal
    goto :end
)

if "%TUNNEL_MODE%"=="quick" (
    echo === starting cloudflared QUICK tunnel ===
    wscript.exe "C:\Users\Ratanshila\Documents\autmated trading\tools\run_hidden.vbs" "cmd /c cd /d C:\Users\Ratanshila\Documents\autmated trading && tools\cloudflared.exe tunnel --url http://localhost:5005 1>> logs\cloudflared.out 2>> logs\cloudflared.err"
    goto :wait_quick_url
)

if "%TUNNEL_MODE%"=="named" (
    echo === starting cloudflared NAMED tunnel ===
    wscript.exe "C:\Users\Ratanshila\Documents\autmated trading\tools\run_hidden.vbs" "cmd /c cd /d C:\Users\Ratanshila\Documents\autmated trading && tools\cloudflared.exe tunnel --config config\cloudflared.yml run 1>> logs\cloudflared.out 2>> logs\cloudflared.err"
    goto :report_named
)

if "%TUNNEL_MODE%"=="ngrok" (
    echo === starting ngrok tunnel ===
    for /f "delims=" %%d in ('.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os; print((os.getenv('NGROK_DOMAIN') or '').strip())"') do set "NGROK_DOMAIN=%%d"
    REM Use !NGROK_DOMAIN! (delayed expansion) — %NGROK_DOMAIN% would expand
    REM at parse time before the for/f populates it.
    if "!NGROK_DOMAIN!"=="" (
        echo [X] NGROK_DOMAIN not set in config\.env
        exit /b 7
    )
    wscript.exe "C:\Users\Ratanshila\Documents\autmated trading\tools\run_hidden.vbs" "cmd /c cd /d C:\Users\Ratanshila\Documents\autmated trading && ngrok http 5005 --domain=!NGROK_DOMAIN! --log=stdout 1>> logs\ngrok.out 2>> logs\ngrok.err"
    goto :report_ngrok
)

echo [X] unknown TUNNEL_MODE=%TUNNEL_MODE% (expected: quick / named / ngrok / none)
exit /b 8

REM ── quick-tunnel: scrape random URL from cloudflared.err ──
:wait_quick_url
echo === waiting for quick tunnel URL (up to 20s) ===
set TUNNEL_URL=
for /l %%i in (1,1,20) do (
    ping 127.0.0.1 -n 2 >nul
    for /f "tokens=*" %%u in ('powershell -NoProfile -Command "$txt = (Get-Content 'logs\cloudflared.err' -Raw -ErrorAction SilentlyContinue); if ($txt -match 'https://[a-z0-9\-]+\.trycloudflare\.com') { $matches[0] }"') do set TUNNEL_URL=%%u
    if defined TUNNEL_URL goto :got_quick_url
)
:got_quick_url
echo.
if defined TUNNEL_URL (
    echo === DONE — webhook + QUICK tunnel LIVE ===
    echo   PUBLIC URL: %TUNNEL_URL%
    echo   POST       %TUNNEL_URL%/tv-signal
    echo   GET        %TUNNEL_URL%/health
    echo.
    echo   ⚠  This URL ROTATES on every restart. To make it permanent see
    echo      docs\STABLE_TUNNEL_SETUP.md
) else (
    echo [!] tunnel URL not visible yet — re-check in 10s:
    echo     powershell -NoProfile -Command "Get-Content -Path 'logs\cloudflared.err' -Tail 30"
)
goto :end

REM ── named-tunnel: read TV_PUBLIC_URL from .env ──
:report_named
ping 127.0.0.1 -n 5 >nul
for /f "delims=" %%u in ('.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os; print((os.getenv('TV_PUBLIC_URL') or '').strip())"') do set "TV_PUBLIC_URL=%%u"
echo.
echo === DONE -- webhook + NAMED tunnel LIVE ===
if "!TV_PUBLIC_URL!"=="" (
    echo   [!] TV_PUBLIC_URL not set in config\.env -- paste your stable hostname there.
) else (
    echo   PUBLIC URL: !TV_PUBLIC_URL!
    echo   POST       !TV_PUBLIC_URL!/tv-signal
    echo   GET        !TV_PUBLIC_URL!/health
    echo.
    echo   [OK] This URL is STABLE across restarts. TV alerts stay valid.
)
goto :end

REM ── ngrok: TV_PUBLIC_URL or NGROK_DOMAIN-derived ──
:report_ngrok
ping 127.0.0.1 -n 5 >nul
for /f "delims=" %%u in ('.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os; u=(os.getenv('TV_PUBLIC_URL') or '').strip(); d=(os.getenv('NGROK_DOMAIN') or '').strip(); print(u or (('https://'+d) if d else ''))"') do set "TV_PUBLIC_URL=%%u"
echo.
echo === DONE -- webhook + NGROK tunnel LIVE ===
if "!TV_PUBLIC_URL!"=="" (
    echo   [!] TV_PUBLIC_URL / NGROK_DOMAIN not set in config\.env.
) else (
    echo   PUBLIC URL: !TV_PUBLIC_URL!
    echo   POST       !TV_PUBLIC_URL!/tv-signal
    echo.
    echo   [OK] This URL is STABLE across restarts ^(ngrok reserved domain^).
)
goto :end

:end
echo.
