@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============== WHY NO TRADE INVESTIGATION ==============
echo.
echo --- 1. Last 15 webhook events (with event type) ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; [print(f'  {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\")}  {r.get(\"event\",\"?\"):<22} sym={r.get(\"symbol\",\"-\"):<8} dir={r.get(\"direction\",\"-\"):<5} reason={r.get(\"reason\",r.get(\"error\",\"\"))[:50]}') for r in lines[-15:]]"
echo.
echo --- 2. Gate block events (last 50 lines) ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; blocks=[r for r in lines if 'gate_block' in r.get('event','') or 'gate_' in r.get('event','')]; print(f'  Total gate events: {len(blocks)}'); [print(f'  {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\")}  {r.get(\"event\")}: sym={r.get(\"symbol\",\"-\")} dir={r.get(\"direction\",\"-\")} reason={r.get(\"reason\",r.get(\"error\",\"\"))[:80]}') for r in blocks[-10:]]"
echo.
echo --- 3. Webhook stats (since restart) ---
.venv\Scripts\python.exe -c "import urllib.request as u, json; d=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8).read().decode()); m=d['metrics']; print(f'  requests_total={m.get(\"requests_total\",0)}'); print(f'  writes_ok    ={m.get(\"writes_ok\",0)}'); print(f'  rejected     ={m.get(\"rejected\",0)}'); print(f'  duplicates   ={m.get(\"duplicates\",0)}'); print(f'  auth_fails   ={m.get(\"auth_fails\",0)}'); print(f'  dryruns      ={m.get(\"dryruns\",0)}')"
echo.
echo --- 4. Current MT5 positions (correlation gate input) ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); pos=mt5.positions_get() or []; from collections import Counter; c=Counter((p.symbol,'BUY' if p.type==0 else 'SELL') for p in pos); print(f'  Open positions by (sym,dir): {dict(c) or \"none\"}'); ai=mt5.account_info(); print(f'  Equity ${ai.equity:.2f} / SoD?'); mt5.shutdown()"
echo.
echo --- 5. brain_state.json — SoD equity (DD gate input) ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; s=json.loads(Path('logs/brain_state.json').read_text()); print(f'  start_of_day_equity: {s.get(\"start_of_day_equity\")}'); print(f'  trading_paused: {s.get(\"trading_paused\")}'); print(f'  drawdown_lockout_until: {s.get(\"drawdown_lockout_until\")}')"
echo.
echo --- 6. Today's news_calendar entries ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; cal=json.loads(Path('config/news_calendar.json').read_text()) if Path('config/news_calendar.json').exists() else []; today=datetime.now().date(); todays=[e for e in cal if e.get('time','').startswith(str(today))]; print(f'  Today entries: {len(todays)}'); [print(f'    {e.get(\"time\")}  {e.get(\"impact\",\"?\"):<6} {e.get(\"event\",e.get(\"title\",\"\"))[:60]}') for e in todays[:10]]"
echo.
echo --- 7. Signal files in MT5 (was anything written recently?) ---
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals*.json' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | Select-Object Name, LastWriteTime, @{N='AgeMin';E={[math]::Round((Get-Date - $_.LastWriteTime).TotalMinutes,1)}} | Format-Table"
