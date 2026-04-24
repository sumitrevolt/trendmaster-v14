@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === killing any python.exe ===
taskkill /F /IM python.exe 2>nul
ping 127.0.0.1 -n 3 >nul

echo === clearing lock + truncating logs ===
del /f /q logs\brain.lock 2>nul
type nul > logs\trend_master_brain.out
type nul > logs\trend_master_brain.err

echo === nuking pycache ===
rmdir /s /q ai_trading_agents\__pycache__ 2>nul
rmdir /s /q config\__pycache__ 2>nul
rmdir /s /q tools\__pycache__ 2>nul

echo === starting brain detached ===
start "TrendMaster Brain - LIVE" /MIN cmd /c "title TrendMaster Brain - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py 1>> logs\trend_master_brain.out 2>> logs\trend_master_brain.err"

echo === wait 15s for boot ===
ping 127.0.0.1 -n 16 >nul

echo === DONE - check find_brain.cmd for status ===
