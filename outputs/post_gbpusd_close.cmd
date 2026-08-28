@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============== POST-CLOSE STATE ==============
echo.
echo --- 1. Current MT5 positions + long-USD count ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  Account:  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}'); print(f'  Positions: {len(pos)}'); long_usd=0; short_usd=0; long_usd_pairs={'USDJPY':'BUY','USDCHF':'BUY','USDCAD':'BUY','EURUSD':'SELL','GBPUSD':'SELL','AUDUSD':'SELL','NZDUSD':'SELL','XAUUSD':'SELL','XAGUSD':'SELL','BTCUSD':'SELL'}; [print(f'    {p.symbol} {(\"BUY\" if p.type==0 else \"SELL\")} pnl=${p.profit:.2f}') for p in pos]; long_usd=sum(1 for p in pos if long_usd_pairs.get(p.symbol)==('BUY' if p.type==0 else 'SELL')); short_usd=sum(1 for p in pos if long_usd_pairs.get(p.symbol)!=('BUY' if p.type==0 else 'SELL') and p.symbol in long_usd_pairs); print(f'  long-USD count:  {long_usd}/3  ({\"FULL\" if long_usd>=3 else f\"{3-long_usd} slot(s) free\"})'); print(f'  short-USD count: {short_usd}/3'); mt5.shutdown()"
echo.
echo --- 2. Last 5 executor log lines ---
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 5"
echo.
echo --- 3. TV alerts state (still 20 active?) ---
.venv\Scripts\python.exe -c "import urllib.request as u, json; r=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8).read().decode()); m=r['metrics']; print(f'  webhook: writes={m[\"writes_ok\"]}  rejected={m[\"rejected\"]}  uptime since last restart')"
echo.
echo --- 4. Last real Rocket Prime fire ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; reals=[r for r in lines if r.get('event')=='write_ok' and 'rocket_prime' in str(r.get('tv_strategy',''))]; r=reals[-1] if reals else None; print(f'  Last real fire: {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\")  if r else \"none\"}  {r.get(\"symbol\") if r else \"\"} {r.get(\"direction\") if r else \"\"} tf={r.get(\"tv_timeframe\") if r else \"\"}')"
