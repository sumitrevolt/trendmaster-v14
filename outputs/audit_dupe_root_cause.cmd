@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\audit_dupe_root_cause.py" > "%~dp0\..\logs\audit_dupe_root_cause.log" 2>&1
type "%~dp0\..\logs\audit_dupe_root_cause.log"
echo.
timeout /t 30 /nobreak > nul
