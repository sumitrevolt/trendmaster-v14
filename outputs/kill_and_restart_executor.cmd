@echo off
cd /d "%~dp0\.."
echo === Aggressive psutil kill of executor ===
.venv\Scripts\python.exe outputs\force_kill_executor.py
echo.
echo === Clean lock files ===
if exist "logs\python_executor.lock" del /Q "logs\python_executor.lock" 2>nul
if exist "logs\.python_executor.lock" del /Q "logs\.python_executor.lock" 2>nul
echo.
echo === Spawn fresh executor (silent via run_hidden.vbs) ===
wscript.exe "tools\run_hidden.vbs" "cmd /c cd /d %~dp0\.. && .venv\Scripts\pythonw.exe tools\python_signal_executor.py"
ping 127.0.0.1 -n 8 >nul
echo.
echo === Recent log ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 8"
echo.
echo Done.
timeout /t 8 /nobreak > nul
