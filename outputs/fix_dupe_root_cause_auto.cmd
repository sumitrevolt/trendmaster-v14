@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\fix_dupe_root_cause_2026-05-09.py" > "%~dp0\..\logs\fix_dupe_root_cause.log" 2>&1
type "%~dp0\..\logs\fix_dupe_root_cause.log"
echo.
timeout /t 30 /nobreak > nul
