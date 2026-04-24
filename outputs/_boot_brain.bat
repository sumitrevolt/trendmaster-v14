@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
taskkill /F /FI "WINDOWTITLE eq TrendMaster Brain - LIVE" 2>nul
del /f /q logs\brain.lock 2>nul
rmdir /s /q ai_trading_agents\__pycache__ 2>nul
rmdir /s /q config\__pycache__ 2>nul
type nul > logs\trend_master_brain.out
type nul > logs\trend_master_brain.err
start "TrendMaster Brain - LIVE" /MIN cmd /c "title TrendMaster Brain - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py 1>> logs\trend_master_brain.out 2>> logs\trend_master_brain.err"
echo BOOT_DISPATCHED
