@echo off
REM Wrapper invoked by Claude scheduled task / Windows schtasks.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe tools\walkforward_lab.py --symbol all >> logs\walkforward_lab.log 2>&1
