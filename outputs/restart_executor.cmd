@echo off
echo === Killing executor (Health Watchdog will respawn within 60s) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host '  killing executor PID' $_.ProcessId; taskkill /F /T /PID $_.ProcessId 2>$null }"
echo.
echo Waiting 65s for Health Watchdog 1-min cycle to respawn...
timeout /t 65 /nobreak > nul
echo.
echo === Recent executor heartbeats ===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\python_executor.log' -Tail 5"
timeout /t 5 /nobreak > nul
