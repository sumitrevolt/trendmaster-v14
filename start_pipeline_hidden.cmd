@echo off
REM ───────────────────────────────────────────────────────────────────────────
REM  start_pipeline_hidden.cmd — runs webhook + ngrok WITHOUT visible terminals
REM
REM  Uses pythonw.exe (windowless Python) for the receiver, and `start /B` for
REM  ngrok so neither pops a cmd window. Stdout/stderr go to log files only.
REM
REM  Replaces start_tv_webhook.cmd when you don't want any visible windows.
REM ───────────────────────────────────────────────────────────────────────────
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Kill any prior receiver / tunnel
powershell -NoProfile -WindowStyle Hidden -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -in 'python.exe','pythonw.exe' -and $_.CommandLine -like '*tv_webhook_receiver*') -or ($_.Name -eq 'ngrok.exe') -or ($_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*tv_webhook*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 800" >nul 2>&1

REM Truncate logs
del /f /q logs\tv_webhook.log logs\tv_webhook.err logs\tv_webhook.bootstrap.out logs\tv_webhook.bootstrap.err 2>nul
type nul > logs\tv_webhook.bootstrap.out
type nul > logs\tv_webhook.bootstrap.err
type nul > logs\ngrok.out
type nul > logs\ngrok.err

REM Start webhook receiver via pythonw.exe (windowless — NO console)
start "" /B .venv\Scripts\pythonw.exe -u -m ai_trading_agents.tv_webhook_receiver 1>> logs\tv_webhook.bootstrap.out 2>> logs\tv_webhook.bootstrap.err

REM Wait for receiver to bind
ping 127.0.0.1 -n 4 >nul

REM Start ngrok hidden via /B flag (no new window). Use full path to the
REM winget-installed binary (NOT tools\ngrok.exe which doesn't exist).
REM The authtoken lives in %LOCALAPPDATA%\ngrok\ngrok.yml — picked up automatically.
start "" /B "C:\Users\Ratanshila\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe" http 5005 --domain=shadow-cosmos-unending.ngrok-free.dev --log=stdout 1>> logs\ngrok.out 2>> logs\ngrok.err

ping 127.0.0.1 -n 4 >nul

REM Verify receiver health
.venv\Scripts\python.exe -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5005/health',timeout=3); print('LOCAL:',r.read().decode())" 2>nul

REM Verify public health
.venv\Scripts\python.exe -c "import urllib.request; r=urllib.request.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health',timeout=10); print('PUBLIC:',r.read().decode())" 2>nul

echo === pipeline up (hidden) ===
