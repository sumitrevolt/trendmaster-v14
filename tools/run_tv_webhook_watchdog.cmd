@echo off
REM Wrapper invoked by Windows Task Scheduler. Mirrors run_zero_trades_watchdog.cmd.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe tools\tv_webhook_watchdog.py >> logs\tv_webhook_watchdog.log 2>&1
