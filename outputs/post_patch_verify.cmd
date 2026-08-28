@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Brain alive? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Measure-Object | Select-Object @{N='BrainProcs';E={$_.Count}}"
echo.
echo === Webhook + ngrok alive? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | Measure-Object | Select-Object @{N='WebhookProcs';E={$_.Count}}"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='ngrok.exe'\" | Measure-Object | Select-Object @{N='NgrokProcs';E={$_.Count}}"
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  Public health:', r.status)"
echo.
echo === MT5 + positions ===
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  pos={len(pos)}'); [print(f'    {p.symbol} {(\"BUY\" if p.type==0 else \"SELL\")} pnl=${p.profit:.2f}') for p in pos]; mt5.shutdown()"
echo.
echo === New gates causing issues? (check tv_signals.jsonl since 21:30) ===
.venv\Scripts\python.exe -c "from pathlib import Path; import json, datetime as dt; lines=Path('logs/tv_signals.jsonl').read_text().splitlines(); cutoff=1778080000; recent=[json.loads(l) for l in lines if 'event' in l]; recent=[r for r in recent if r.get('ts',0) > cutoff]; events={}; [events.update({r.get('event','?'): events.get(r.get('event','?'),0)+1}) for r in recent]; print('  Recent events:', dict(events) or '(none in window)')"
echo.
echo === Brain watchpet log (any alerts?) ===
powershell -NoProfile -Command "Get-Content 'logs\watchpet_brain.log' -Tail 5 -ErrorAction SilentlyContinue"
echo.
echo === Pre-commit guard test ===
.venv\Scripts\python.exe tools\check_no_resolve.py
echo.
echo === Outputs/ dir size ===
powershell -NoProfile -Command "$d='outputs'; '  ' + [string](Get-ChildItem $d -File | Measure-Object).Count + ' top-level files, ' + [string](Get-ChildItem $d -Recurse -File | Measure-Object).Count + ' total (incl _session_scratch)'"
