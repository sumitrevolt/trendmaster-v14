@echo off
REM Start the Telegram direction listener (long-running, hidden).
REM Kills any existing instance first.
cd /d "%~dp0\.."

echo === Stopping any existing telegram_direction_listener ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*telegram_direction_listener*' } | ForEach-Object { Write-Host '  killing PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

ping 127.0.0.1 -n 3 >nul

echo === Starting telegram_direction_listener (hidden) ===
wscript.exe "tools\hidden_telegram_direction_listener.vbs"
ping 127.0.0.1 -n 5 >nul

echo === Verifying ===
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*telegram_direction_listener*' }; if ($procs) { Write-Host '[OK] listener running, PIDs:' $procs.ProcessId } else { Write-Host '[X] listener not detected' }"
echo.
timeout /t 10 /nobreak > nul
