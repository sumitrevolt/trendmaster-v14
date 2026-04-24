@echo off
REM Wrapper invoked by Windows Task Scheduler. Exists so schtasks /tr
REM can point at a single path instead of juggling cmd-quoting hell.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe tools\zero_trades_watchdog.py >> logs\zero_trades_watchdog.log 2>&1
