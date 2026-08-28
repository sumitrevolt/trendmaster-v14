@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Kill all python_signal_executor instances (singleton will respawn cleanly) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 4 >nul
echo.
echo === Verify zero executors running ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Measure-Object | Select-Object @{N='AfterKill';E={$_.Count}}"
echo.
echo === Spawn fresh executor (will pick up patched skip-reason logs) ===
start "" /MIN cmd /c ".venv\Scripts\pythonw.exe tools\python_signal_executor.py"
ping 127.0.0.1 -n 6 >nul
echo.
echo === Confirm new executor alive ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table"
echo.
echo === Tail last 10 lines of executor log ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 10"
