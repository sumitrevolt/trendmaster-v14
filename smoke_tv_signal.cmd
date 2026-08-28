@echo off
REM ───────────────────────────────────────────────────────────────────────────
REM  smoke_tv_signal.cmd  —  one-line probe of the TV → MT5 pipeline.
REM
REM  Fires a single test signal (default: XAUUSD M15 BUY) at the LOCAL
REM  webhook receiver and tails the audit log to confirm it round-tripped.
REM  Use this whenever you want a 5-second sanity check that the pipeline
REM  is alive end-to-end without waiting for a real TradingView alert.
REM
REM  Usage:
REM      smoke_tv_signal.cmd                          (XAUUSD M15 BUY)
REM      smoke_tv_signal.cmd EURUSD H1 SELL
REM      smoke_tv_signal.cmd BTCUSD M5 BUY
REM ───────────────────────────────────────────────────────────────────────────
setlocal
pushd "%~dp0"

set "SYM=%~1"
set "TF=%~2"
set "DIR=%~3"
if "%SYM%"=="" set "SYM=XAUUSD"
if "%TF%"=="" set "TF=M15"
if "%DIR%"=="" set "DIR=BUY"

echo === firing smoke signal: %SYM% %TF% %DIR% (source=smoke_test) ===
.venv\Scripts\python.exe -c "import os, json, time, urllib.request, sys; from dotenv import load_dotenv; load_dotenv('config/.env'); s=(os.getenv('TV_WEBHOOK_SECRET') or '').strip(); host=os.getenv('TV_WEBHOOK_HOST','127.0.0.1'); port=os.getenv('TV_WEBHOOK_PORT','5005'); url=f'http://{host}:{port}/tv-signal'; body=json.dumps({'secret':s,'symbol':'%SYM%','direction':'%DIR%','tv_strategy':'smoke_test','tv_alert_ts':int(time.time()),'tv_timeframe':'%TF%'}).encode(); req=urllib.request.Request(url, data=body, method='POST', headers={'Content-Type':'application/json'}); r=urllib.request.urlopen(req, timeout=8); print('  HTTP', r.status, '-', r.read().decode())"
if errorlevel 1 (
    echo [X] Smoke signal failed. Common causes:
    echo     - webhook receiver not running        (run: start_tv_webhook.cmd)
    echo     - TV_WEBHOOK_SECRET missing in .env   (check: config\.env)
    echo     - symbol not whitelisted              (check: ai_trading_agents\team_params.py)
    popd
    exit /b 1
)

echo.
echo === last 5 lines of logs\tv_signals.jsonl ===
powershell -NoProfile -Command "if (Test-Path 'logs\tv_signals.jsonl') { Get-Content -Path 'logs\tv_signals.jsonl' -Tail 5 } else { Write-Host '(no audit log yet)' }"

echo.
echo === MT5 signal file mtime check ===
powershell -NoProfile -Command "$p='C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals.json'; if ($p -and (Test-Path $p)) { $i=Get-Item $p; Write-Host ('  ' + $p); Write-Host ('  last write: ' + $i.LastWriteTime) } else { $alt='trendmaster_signals.json'; if (Test-Path $alt) { Write-Host ('  fallback: ' + (Resolve-Path $alt)); Write-Host ('  last write: ' + (Get-Item $alt).LastWriteTime) } else { Write-Host '  [!] signal file not found at MT5 path or project root' } }"

popd
endlocal
