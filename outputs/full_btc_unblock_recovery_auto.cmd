@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\full_btc_unblock_recovery.py" > "%~dp0\..\logs\full_btc_unblock_recovery.log" 2>&1
type "%~dp0\..\logs\full_btc_unblock_recovery.log"
echo.
timeout /t 30 /nobreak > nul
