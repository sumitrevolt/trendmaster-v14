@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============== STEP 1: Restart executor with env-load patch ==============
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 4 >nul
start "" /MIN cmd /c ".venv\Scripts\pythonw.exe tools\python_signal_executor.py"
ping 127.0.0.1 -n 8 >nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Measure-Object | Select-Object @{N='ExecAlive';E={$_.Count}}"
echo.
echo ============== STEP 2: Trigger log rotation manually ==============
.venv\Scripts\python.exe tools\daily_maintenance.py
echo.
echo ============== STEP 3: Verify log sizes after rotation ==============
powershell -NoProfile -Command "$total=(Get-ChildItem 'logs' -Recurse -File | Measure-Object Length -Sum).Sum; Write-Host ('  Total logs: {0:N1} MB' -f ($total/1MB)); Get-ChildItem 'logs' -File | Sort-Object Length -Descending | Select-Object -First 6 | ForEach-Object { Write-Host ('  ' + $_.Name + ': {0:N1} MB' -f ($_.Length/1MB)) }"
echo.
echo ============== STEP 4: Final state summary ==============
echo --- Processes ---
powershell -NoProfile -Command "$brain=(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' }).Count; $webhook=(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' }).Count; $exec=(Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' }).Count; Write-Host ('  brain=' + $brain + '  webhook=' + $webhook + '  executor=' + $exec)"
echo.
echo --- Account ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  positions={len(pos)}'); mt5.shutdown()"
echo.
echo --- TG test from new executor path ---
.venv\Scripts\python.exe -c "from ai_trading_agents.telegram_notifier import get_notifier; n=get_notifier(); ok=n.send('TG-final-test from executor path 2026-05-07'); print('  TG send result:', ok)"
