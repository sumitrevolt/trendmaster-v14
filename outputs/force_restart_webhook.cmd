@echo off
REM Force kill webhook PIDs by command-line match, then spawn fresh.
cd /d "%~dp0\.."
echo === Force-restart TV webhook (load patched code) ===

REM Kill via PowerShell process matching
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { Write-Host '  killing webhook PID' $_.ProcessId; taskkill /F /T /PID $_.ProcessId 2>$null }"

ping 127.0.0.1 -n 4 >nul

echo === Spawning fresh webhook (silent via run_hidden.vbs) ===
wscript.exe "tools\run_hidden.vbs" "cmd /c cd /d %~dp0\.. && .venv\Scripts\pythonw.exe -m ai_trading_agents.tv_webhook_receiver"
ping 127.0.0.1 -n 6 >nul

echo === Health check ===
curl -s http://127.0.0.1:5005/health
echo.
timeout /t 10 /nobreak > nul
