@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Restart webhook with new dryrun patch ===
call start_tv_webhook.cmd
echo.
echo === Test 1: dryrun=1 (should NOT write MT5 file) ===
.venv\Scripts\python.exe -c "import urllib.request as u; req=u.Request('https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=XAUUSD&tf=5&dryrun=1', data=b'Buy Observation @ 1.0', headers={'Content-Type':'text/plain'}, method='POST'); print('  HTTP', u.urlopen(req, timeout=8).status, '|', u.urlopen(req, timeout=8).read().decode()[:200])"
echo.
echo === Test 2: verify NO MT5 file written ===
.venv\Scripts\python.exe -c "from pathlib import Path; p=Path(r'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_XAUUSD.json'); print('  trendmaster_signals_XAUUSD.json exists:', p.exists())"
echo.
echo === Test 3: positions still zero ===
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); pos=mt5.positions_get() or []; print(f'  positions: {len(pos)}'); ai=mt5.account_info(); print(f'  balance: ${ai.balance:.2f}  equity: ${ai.equity:.2f}'); mt5.shutdown()"
echo.
echo === Webhook stats ===
.venv\Scripts\python.exe -c "import urllib.request as u, json; d=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8).read().decode()); m=d['metrics']; print(f'  requests={m.get(\"requests_total\",0)}  writes_ok={m.get(\"writes_ok\",0)}  dryruns={m.get(\"dryruns\",0)}  rejected={m.get(\"rejected\",0)}')"
