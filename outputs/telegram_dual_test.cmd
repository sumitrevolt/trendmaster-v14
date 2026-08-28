@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\telegram_dual_test.py" > "%~dp0\..\logs\telegram_dual_test.log" 2>&1
type "%~dp0\..\logs\telegram_dual_test.log"
echo.
timeout /t 30 /nobreak > nul
