@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe tools\health_watchdog.py --once > outputs\watchdog_once.log 2>&1
