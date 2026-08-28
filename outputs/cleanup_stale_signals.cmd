@echo off
cd /d "%~dp0\.."
.venv\Scripts\python.exe outputs\cleanup_stale_signals.py > outputs\cleanup_result.txt 2>&1
type outputs\cleanup_result.txt
timeout /t 8 /nobreak > nul
