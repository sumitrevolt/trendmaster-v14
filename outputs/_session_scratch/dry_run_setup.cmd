@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === import sanity ===
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'tools/tv_alert_setup'); import setup_tv_alerts as s; import delete_all_alerts as d; import reset_and_create as r; print('all 3 modules import OK')"
echo.
echo === alerts_config dry-run ===
.venv\Scripts\python.exe tools\tv_alert_setup\setup_tv_alerts.py --dry-run
