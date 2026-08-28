@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\telegram_diagnose_2026-05-09.py" > "%~dp0\..\logs\telegram_diagnose.log" 2>&1
type "%~dp0\..\logs\telegram_diagnose.log"
echo.
timeout /t 30 /nobreak > nul
