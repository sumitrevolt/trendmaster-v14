@echo off
REM Auto-running diagnostic (no pause) — output captured to log file.
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\diag_status_2026-05-09.py" > "%~dp0\..\logs\diag_status_run.log" 2>&1
type "%~dp0\..\logs\diag_status_run.log"
echo.
echo === diag complete — log saved to logs\diag_status_run.log ===
timeout /t 60 /nobreak > nul
