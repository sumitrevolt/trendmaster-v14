@echo off
REM Wrapper invoked by Windows Task Scheduler. Exists so schtasks /tr
REM can point at a single path instead of juggling cmd-quoting hell.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe tools\ea_parity_nightly.py >> logs\ea_parity_nightly.log 2>&1
