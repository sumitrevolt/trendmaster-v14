@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Kill all executor instances ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 4 >nul
echo.
echo === Verify zero ===
powershell -NoProfile -Command "$n=(Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' }).Count; Write-Host ('  remaining: ' + $n)"
echo.
echo === Spawn fresh executor (will load fresh .env) ===
start "" /MIN cmd /c ".venv\Scripts\pythonw.exe tools\python_signal_executor.py"
ping 127.0.0.1 -n 8 >nul
echo.
echo === Confirm new executor up ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table"
echo.
echo === Tail latest log to confirm Telegram init message ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 8"
