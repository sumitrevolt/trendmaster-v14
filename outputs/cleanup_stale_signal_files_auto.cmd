@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\cleanup_stale_signal_files.py" > "%~dp0\..\logs\cleanup_stale_signal_files.log" 2>&1
type "%~dp0\..\logs\cleanup_stale_signal_files.log"
echo.
timeout /t 30 /nobreak > nul
