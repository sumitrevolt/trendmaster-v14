@echo off
cd /d "%~dp0\.."
.venv\Scripts\python.exe outputs\diag_mt5_data_path.py > outputs\diag_mt5_result.txt 2>&1
type outputs\diag_mt5_result.txt
timeout /t 10 /nobreak > nul
