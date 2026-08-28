@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
".venv\Scripts\python.exe" "outputs\restart_executor.py"
".venv\Scripts\python.exe" "outputs\restart_dash_v2.py"
echo --- executor status ---
type outputs\restart_executor_status.json
echo.
echo --- dash status ---
type outputs\restart_dash_status.log
