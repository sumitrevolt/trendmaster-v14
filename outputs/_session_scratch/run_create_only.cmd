@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Skip delete, run create-only loop ===
.venv\Scripts\python.exe tools\tv_alert_setup\reset_and_create.py --skip-delete
