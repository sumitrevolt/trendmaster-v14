@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\full_btc_unblock_2026-05-09.py" > "%~dp0\..\logs\full_btc_unblock.log" 2>&1
type "%~dp0\..\logs\full_btc_unblock.log"
echo.
timeout /t 60 /nobreak > nul
