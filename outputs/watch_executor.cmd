@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Wait 60 sec for executor to make several poll iterations ===
ping 127.0.0.1 -n 61 >nul
echo.
echo === Last 30 log lines (should show patched skip reasons if signals tried) ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 30"
echo.
echo === Specifically search for "skip" patterns ===
powershell -NoProfile -Command "Select-String -Path 'logs\python_executor.log' -Pattern '\[INFO\] skip|\[INFO\] SAFEGUARD' | Select-Object -Last 15 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === Send a TEST signal via webhook with REAL price (will trigger trade attempt) ===
echo === This creates ONE GBPUSD SELL with current market price ===
.venv\Scripts\python.exe -c "import urllib.request as u, os; from dotenv import load_dotenv; load_dotenv('config/.env'); secret=os.getenv('TV_WEBHOOK_SECRET'); url=f'https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={secret}&symbol=GBPUSD&tf=15'; req=u.Request(url, data=b'Sell Observation @ 1.35850', headers={'Content-Type':'text/plain'}, method='POST'); print('  HTTP', u.urlopen(req, timeout=8).status)"
echo.
echo === Wait 15 sec for executor to pick up the signal ===
ping 127.0.0.1 -n 16 >nul
echo.
echo === Latest log lines (should show the GBPUSD attempt + reason) ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 20"
echo.
echo === Check if a new GBPUSD position opened ===
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); pos=mt5.positions_get() or []; print(f'  positions: {len(pos)}'); [print(f'    {p.symbol} {(\"BUY\" if p.type==0 else \"SELL\")} pnl=${p.profit:.2f}') for p in pos]; mt5.shutdown()"
