@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\verify_singleton_logical.py" > "%~dp0\..\logs\verify_singleton_logical.log" 2>&1
type "%~dp0\..\logs\verify_singleton_logical.log"
echo.
timeout /t 30 /nobreak > nul
