@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === killing any stray python.exe ===
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo === nuking pycache ===
rmdir /s /q ai_trading_agents\__pycache__ 2>nul
rmdir /s /q config\__pycache__ 2>nul
rmdir /s /q tools\__pycache__ 2>nul

echo === clearing lock and logs ===
del /f /q logs\brain.lock 2>nul
type nul > logs\trend_master_brain.out
type nul > logs\trend_master_brain.err

echo === starting brain in background ===
start "TrendMaster Brain - LIVE" /MIN cmd /c "title TrendMaster Brain - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py 1>> logs\trend_master_brain.out 2>> logs\trend_master_brain.err"

echo === waiting 12s for brain to boot ===
timeout /t 12 /nobreak >nul

echo === verify pycache regenerated (means brain loaded fresh) ===
dir /od ai_trading_agents\__pycache__\*.pyc 2>nul

echo === DONE ===
