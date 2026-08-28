@echo off
REM Force restart python_signal_executor.
REM Kills any running instance, removes stale lock file, spawns fresh.
cd /d "%~dp0\.."
echo === Force-restart python_signal_executor ===

REM Kill any existing executor PIDs
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host '  killing executor PID' $_.ProcessId; taskkill /F /T /PID $_.ProcessId 2>$null }"

REM Wait for kill to settle
ping 127.0.0.1 -n 5 >nul

REM Clean up stale lock file
if exist "logs\python_executor.lock" del /Q "logs\python_executor.lock" 2>nul
if exist "logs\.python_executor.lock" del /Q "logs\.python_executor.lock" 2>nul

echo === Spawning fresh executor (silent via run_hidden.vbs) ===
wscript.exe "tools\run_hidden.vbs" "cmd /c cd /d %~dp0\.. && .venv\Scripts\pythonw.exe tools\python_signal_executor.py"
ping 127.0.0.1 -n 8 >nul

echo.
echo === Recent executor heartbeats ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 8"
echo.
echo Done.
timeout /t 10 /nobreak > nul
