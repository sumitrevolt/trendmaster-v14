@echo off
REM Full restart: webhook (load async OCR patch) + executor (load whitelist update).
cd /d "%~dp0\.."
echo === 1/3: Kill webhook ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { Write-Host '  killing webhook PID' $_.ProcessId; taskkill /F /T /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 4 >nul

echo === 2/3: Kill executor ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host '  killing executor PID' $_.ProcessId; taskkill /F /T /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 4 >nul

REM Clean stale lock files
if exist "logs\python_executor.lock" del /Q "logs\python_executor.lock" 2>nul
if exist "logs\.python_executor.lock" del /Q "logs\.python_executor.lock" 2>nul

echo === 3/3: Spawn fresh webhook + executor (silent via run_hidden.vbs) ===
wscript.exe "tools\run_hidden.vbs" "cmd /c cd /d %~dp0\.. && .venv\Scripts\pythonw.exe -m ai_trading_agents.tv_webhook_receiver"
ping 127.0.0.1 -n 4 >nul
wscript.exe "tools\run_hidden.vbs" "cmd /c cd /d %~dp0\.. && .venv\Scripts\pythonw.exe tools\python_signal_executor.py"
ping 127.0.0.1 -n 8 >nul

echo.
echo === Webhook health ===
curl -s http://127.0.0.1:5005/health
echo.
echo.
echo === Recent webhook log ===
powershell -NoProfile -Command "Get-Content 'logs\tv_webhook.log' -Tail 5"
echo.
echo === Recent executor log ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 5"
echo.
echo Done.
timeout /t 10 /nobreak > nul
