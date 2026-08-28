@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo ============== XAUUSD DIRECTION MISMATCH DEBUG ==============
echo.
echo --- 1. ALL XAUUSD signals last 4 hours (with FULL src + direction) ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json, time; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; cutoff=time.time()-14400; xau=[r for r in lines if r.get('symbol')=='XAUUSD' and r.get('ts',0)>cutoff]; print(f'Total: {len(xau)}'); [print(f'  {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\"):>10}  event={r.get(\"event\",\"?\"):<14} dir={r.get(\"direction\",\"-\"):<5} tf={r.get(\"tv_timeframe\",\"-\"):<4} conf={r.get(\"confidence\",0):.2f} src={r.get(\"tv_strategy\",\"?\")[:30]}') for r in xau]"
echo.
echo --- 2. XAUUSD raw bodies log (what TV actually sent) ---
powershell -NoProfile -Command "if (Test-Path 'logs\tv_webhook_unparsed_bodies.log') { Get-Content 'logs\tv_webhook_unparsed_bodies.log' -Tail 30 } else { 'no unparsed bodies log (means all bodies were parseable)' }"
echo.
echo --- 3. Last 30 webhook log lines ---
powershell -NoProfile -Command "Get-Content 'logs\tv_webhook.log' -Tail 30 | Select-String -Pattern 'XAUUSD|TEXT mode|INFERRED' | Select-Object -Last 15 | ForEach-Object { '  ' + $_.Line }"
echo.
echo --- 4. MT5 XAUUSD deals last 4 hours ---
.venv\Scripts\python.exe -c "import os; from datetime import datetime, timedelta; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); end=datetime.now(); start=end-timedelta(hours=4); deals=mt5.history_deals_get(start, end) or []; xau=[d for d in deals if d.symbol=='XAUUSD']; print(f'XAUUSD deals: {len(xau)}'); [print(f'  {datetime.fromtimestamp(d.time).strftime(\"%%H:%%M:%%S\")} {(\"BUY\" if d.type==0 else \"SELL\"):4} entry={d.entry} vol={d.volume} price={d.price:.2f} pnl=${d.profit:.2f} comment={d.comment}') for d in xau]; mt5.shutdown()"
echo.
echo --- 5. Current XAUUSD positions (open) ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); pos=mt5.positions_get(symbol='XAUUSD') or []; print(f'Open XAUUSD: {len(pos)}'); [print(f'  ticket={p.ticket} {(\"BUY\" if p.type==0 else \"SELL\"):4} open={p.price_open:.2f} cur={p.price_current:.2f} pnl=${p.profit:.2f} comment={p.comment}') for p in pos]; mt5.shutdown()"
echo.
echo --- 6. Last 20 executor log lines (XAUUSD specifically) ---
powershell -NoProfile -Command "Select-String -Path 'logs\python_executor.log' -Pattern 'XAUUSD' | Select-Object -Last 15 | ForEach-Object { '  ' + $_.Line }"
