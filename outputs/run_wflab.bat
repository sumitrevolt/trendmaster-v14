@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe tools\walkforward_lab.py --symbol all > outputs\wflab_run.log 2>&1
echo DONE exit=%ERRORLEVEL%
