@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\btc_signal_audit.py" > "%~dp0\..\logs\btc_signal_audit.log" 2>&1
type "%~dp0\..\logs\btc_signal_audit.log"
echo.
timeout /t 30 /nobreak > nul
