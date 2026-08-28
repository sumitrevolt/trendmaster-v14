@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Testing Format B end-to-end (XAUUSD M5 BUY simulation) ===
.venv\Scripts\python.exe -c "import urllib.request as u, urllib.parse as up; url='https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=XAUUSD&tf=5'; body='Buy Observation @ 4636.50'.encode(); req=u.Request(url, data=body, headers={'Content-Type':'text/plain'}, method='POST'); r=u.urlopen(req, timeout=10); print('HTTP', r.status); print('BODY:', r.read().decode()[:500])"
echo.
echo === Last line of tv_signals.jsonl ===
.venv\Scripts\python.exe -c "from pathlib import Path; lines=Path('logs/tv_signals.jsonl').read_text().splitlines(); print(lines[-1] if lines else 'empty')"
echo.
echo === MT5 signal file mtime ===
.venv\Scripts\python.exe -c "from pathlib import Path; import datetime as dt; p=Path('C:/Users/Ratanshila/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Files/trendmaster_signals_XAUUSD.json'); print(p, 'exists:', p.exists()); print('mtime:', dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat() if p.exists() else 'N/A'); print('content:', p.read_text()[:300] if p.exists() else 'N/A')"
