@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
taskkill /PID 27028 /F >nul 2>&1
taskkill /F /IM python.exe /FI "CommandLine eq *optimize_per_pair*" >nul 2>&1
python tools\optimize_fast.py
