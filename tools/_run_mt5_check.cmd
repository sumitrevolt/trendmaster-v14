@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
".venv\Scripts\python.exe" "tools\_check_mt5_status.py" > "logs\_mt5_check.out" 2>&1
echo DONE exit=%ERRORLEVEL%
