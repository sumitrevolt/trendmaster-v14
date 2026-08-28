@echo off
REM Post-restart diagnostic — read-only.
REM Lists TrendMaster processes + open MT5 positions.
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\diag_status_2026-05-09.py"
echo.
pause
