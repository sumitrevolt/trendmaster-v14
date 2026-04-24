@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_r11_kill.out" 2>&1
exit /b
:run
echo ===killing brain via PowerShell===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'name=\"python.exe\"' | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | ForEach-Object { Write-Host ('Killing PID ' + $_.ProcessId + ': ' + $_.CommandLine); Stop-Process -Id $_.ProcessId -Force }"
timeout /t 4 /nobreak >nul
echo ===cleanup===
del /f /q logs\brain.lock 2>nul
rmdir /s /q ai_trading_agents\__pycache__ 2>nul
rmdir /s /q config\__pycache__ 2>nul
type nul > logs\trend_master_brain.out
type nul > logs\trend_master_brain.err
echo ===starting fresh brain===
start "TrendMaster Brain - LIVE" /MIN cmd /c "title TrendMaster Brain - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py 1>> logs\trend_master_brain.out 2>> logs\trend_master_brain.err"
echo ===waiting 22s===
timeout /t 22 /nobreak >nul
echo ===BOOT LOG===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 15"
echo ===ERR===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.err' -Tail 10 -ErrorAction SilentlyContinue"
echo ===USDJPY SIGNAL (should now have require_all_3 + max_spread_atr_pct)===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_USDJPY.json' -ErrorAction SilentlyContinue"
