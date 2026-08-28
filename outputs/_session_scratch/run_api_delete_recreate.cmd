@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === API delete-all + recreate-top5 ===
.venv\Scripts\python.exe tools\tv_alert_setup\delete_all_rocket_then_recreate.py
