@echo off
REM =====================================================================
REM 02_restart_webhook_2026-05-09.cmd
REM
REM Restart the TV webhook receiver so it picks up the new
REM TV_ALLOW_INFERRED=1 setting from config\.env.
REM
REM This does NOT touch ngrok (it's already up via the watchdog).
REM Only kills the python tv_webhook_receiver process and respawns it.
REM =====================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Killing existing tv_webhook_receiver process ===
for /f "tokens=*" %%p in ('powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter ('name = ''python.exe''') | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { $_.ProcessId }"') do taskkill /F /PID %%p 2>nul

ping 127.0.0.1 -n 3 >nul

echo === Starting tv_webhook_receiver (will pick up TV_ALLOW_INFERRED=1) ===
start "TV_Webhook - INFERRED" /MIN cmd /c "title TV_Webhook - INFERRED && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u -m ai_trading_agents.tv_webhook_receiver 1>> logs\tv_webhook.bootstrap.out 2>> logs\tv_webhook.bootstrap.err"

ping 127.0.0.1 -n 4 >nul

echo === Local health check ===
.venv\Scripts\python.exe -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5005/health',timeout=3); print('  /health:',r.read().decode())"
if errorlevel 1 (
    echo [X] receiver did not restart cleanly. Check logs\tv_webhook.bootstrap.err
    exit /b 1
)

echo.
echo [OK] webhook restarted with INFERRED mode enabled.
echo   Tail logs:  powershell -Command "Get-Content 'logs\tv_webhook.log' -Tail 5 -Wait"
echo.
