@echo off
REM Auto-running version (no prompt) — for godmode invocation.
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\fix_duplicate_executor_2026-05-09.py" > "%~dp0\..\logs\fix_duplicate_executor_run.log" 2>&1
type "%~dp0\..\logs\fix_duplicate_executor_run.log"
echo.
echo === fix complete — log saved to logs\fix_duplicate_executor_run.log ===
timeout /t 30 /nobreak > nul
