@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo ===killing any python brain===
wmic process where "name='python.exe' and commandline like '%%trend_master_brain%%'" call terminate 2>nul
timeout /t 3 /nobreak >nul
echo ===cleanup===
del /f /q logs\brain.lock 2>nul
rmdir /s /q ai_trading_agents\__pycache__ 2>nul
rmdir /s /q config\__pycache__ 2>nul
type nul > logs\trend_master_brain.out
type nul > logs\trend_master_brain.err
echo ===starting brain===
start "TrendMaster Brain - LIVE" /MIN cmd /c "title TrendMaster Brain - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py 1>> logs\trend_master_brain.out 2>> logs\trend_master_brain.err"
echo ===waiting 15s===
timeout /t 15 /nobreak >nul
echo ===procs===
wmic process where "name='python.exe'" get processid,commandline 2>nul | findstr /v "^$"
echo ===boot log===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 15"
