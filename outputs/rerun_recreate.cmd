@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Re-running delete+recreate with new tf=URL fix ===
.venv\Scripts\python.exe tools\tv_alert_setup\delete_all_rocket_then_recreate.py
