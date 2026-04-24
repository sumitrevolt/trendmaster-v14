@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo ===killing brain PIDs 12900 and 22800===
taskkill /F /PID 12900 2>nul
taskkill /F /PID 22800 2>nul
timeout /t 4 /nobreak >nul
echo ===cleanup===
del /f /q logs\brain.lock 2>nul
rmdir /s /q ai_trading_agents\__pycache__ 2>nul
rmdir /s /q config\__pycache__ 2>nul
type nul > logs\trend_master_brain.out
type nul > logs\trend_master_brain.err
echo ===starting fresh brain===
start "TrendMaster Brain - LIVE" /MIN cmd /c "title TrendMaster Brain - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py 1>> logs\trend_master_brain.out 2>> logs\trend_master_brain.err"
echo ===waiting 20s for boot===
timeout /t 20 /nobreak >nul
echo ===LOG TAIL===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 20"
echo ===ERR TAIL===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.err' -Tail 15 -ErrorAction SilentlyContinue"
echo ===PROCESSES===
tasklist /FI "IMAGENAME eq python.exe" /NH /FO CSV
