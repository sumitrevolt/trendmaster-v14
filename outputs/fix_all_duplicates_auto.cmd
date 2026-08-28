@echo off
REM Unified duplicate killer — handles executor + trailing-stop in one pass.
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\fix_all_duplicates_2026-05-09.py" > "%~dp0\..\logs\fix_all_duplicates_run.log" 2>&1
type "%~dp0\..\logs\fix_all_duplicates_run.log"
echo.
echo === fix_all_duplicates done ===
timeout /t 60 /nobreak > nul
