@echo off
cd /d "%~dp0\.."
.venv\Scripts\python.exe outputs\cleanup_stale_signals_v3.py > outputs\cleanup_v3_result.txt 2>&1
type outputs\cleanup_v3_result.txt
timeout /t 12 /nobreak > nul
