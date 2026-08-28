@echo off
REM End-to-end deploy of Telegram BUY/SELL button helper.
REM
REM 1. Restart tv_webhook_receiver (loads new no-direction → Telegram path)
REM 2. Start telegram_direction_listener (long-running)
REM 3. Verify both alive
REM 4. Health check public webhook
REM
REM After this, RP signals arrive → Telegram inline buttons → operator taps
REM → bot trades on MT5 (and cTrader if OAuth done).

cd /d "%~dp0\.."

echo.
echo ============================================================
echo   Deploying Telegram BUY/SELL button helper
echo ============================================================
echo.

echo === [1/4] Force-restart tv_webhook_receiver ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { Write-Host '  killing webhook PID' $_.ProcessId; taskkill /F /T /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 4 >nul
start "TrendMaster TV Webhook" /MIN cmd /c "title TV Webhook && cd /d %~dp0\.. && .venv\Scripts\pythonw.exe -m ai_trading_agents.tv_webhook_receiver"
ping 127.0.0.1 -n 6 >nul

echo.
echo === [2/4] Start telegram_direction_listener ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*telegram_direction_listener*' } | ForEach-Object { Write-Host '  killing listener PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 3 >nul
wscript.exe "tools\hidden_telegram_direction_listener.vbs"
ping 127.0.0.1 -n 5 >nul

echo.
echo === [3/4] Verify processes ===
powershell -NoProfile -Command "$webhook = Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' }; if ($webhook) { Write-Host '[OK] webhook PIDs:' $webhook.ProcessId } else { Write-Host '[X] webhook NOT running' }; $listener = Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*telegram_direction_listener*' }; if ($listener) { Write-Host '[OK] listener PIDs:' $listener.ProcessId } else { Write-Host '[X] listener NOT running' }"

echo.
echo === [4/4] Health check ===
curl -s http://127.0.0.1:5005/health
echo.
echo.
echo ============================================================
echo   Deploy complete
echo ============================================================
echo.
echo Next RP signal will trigger:
echo   1. Webhook receives no-direction body
echo   2. Telegram message sent with [BUY] [SELL] [SKIP] buttons
echo   3. Operator taps within 20 min on phone
echo   4. Listener writes signal -^> bot trades on MT5
echo.
echo Test: manually send Telegram a callback (or wait for next RP fire).
echo Watch: type logs\telegram_direction_listener.log
echo.
timeout /t 30 /nobreak > nul
