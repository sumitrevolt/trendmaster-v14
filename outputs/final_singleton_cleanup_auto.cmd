@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\final_singleton_cleanup_2026-05-09.py" > "%~dp0\..\logs\final_singleton_cleanup.log" 2>&1
type "%~dp0\..\logs\final_singleton_cleanup.log"
echo.
timeout /t 30 /nobreak > nul
