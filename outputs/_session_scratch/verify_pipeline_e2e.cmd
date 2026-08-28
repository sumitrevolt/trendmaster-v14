@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === 1. Webhook receiver status ===
.venv\Scripts\python.exe -c "import urllib.request as u, json; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8); d=json.loads(r.read().decode()); print('uptime_s:', d['metrics']['started_at'], 'requests_total:', d['metrics']['requests_total'], 'auth_fails:', d['metrics']['auth_fails'], 'writes_ok:', d['metrics']['writes_ok'])"
echo.
echo === 2. Send test signal for each new pair (BUY) ===
.venv\Scripts\python.exe -c "import urllib.request as u; bases=['XAUUSD','EURUSD','USDJPY','GBPUSD','BTCUSD']; tfs=['5','15','30','60']; tf_lbl={'5':'M5','15':'M15','30':'M30','60':'H1'}; secret='5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14'; ok=0; fail=0; [print(f'  {sym} {tf_lbl[tf]:>3}: HTTP {u.urlopen(u.Request(f\"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={secret}&symbol={sym}&tf={tf}\", data=b\"Buy Observation @ 1.0\", headers={\"Content-Type\":\"text/plain\"}, method=\"POST\"), timeout=8).status}') for sym in bases for tf in tfs[:1]]"
echo.
echo === 3. Last 6 lines of tv_signals.jsonl ===
.venv\Scripts\python.exe -c "from pathlib import Path; lines=Path('logs/tv_signals.jsonl').read_text().splitlines(); [print(l[:200]) for l in lines[-6:]]"
echo.
echo === 4. Final webhook stats ===
.venv\Scripts\python.exe -c "import urllib.request as u, json; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8); d=json.loads(r.read().decode()); print('writes_ok:', d['metrics']['writes_ok'], 'requests_total:', d['metrics']['requests_total'])"
