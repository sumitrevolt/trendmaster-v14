@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe outputs\check_and_restart_dashboard.py > outputs\dash_cmd_stdout.txt 2>&1
echo Done.
