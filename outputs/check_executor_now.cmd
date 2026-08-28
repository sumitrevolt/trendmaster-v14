@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Last 30 executor log lines ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 30"
echo.
echo === Look for any patched skip-reason logs ===
powershell -NoProfile -Command "Select-String -Path 'logs\python_executor.log' -Pattern 'skip .* in cooldown|skip .* already have|skip .* cap reached|SAFEGUARD BLOCK' | Select-Object -Last 10 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === Account state ===
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  positions: {len(pos)}, equity: ${ai.equity:.2f}'); mt5.shutdown()"
