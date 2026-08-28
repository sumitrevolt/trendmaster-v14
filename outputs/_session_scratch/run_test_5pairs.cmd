@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Test 5 pairs x 2 TFs (10 webhook calls) ===
.venv\Scripts\python.exe outputs\test_5pairs.py
echo.
echo === Webhook final stats ===
.venv\Scripts\python.exe -c "import urllib.request as u, json; d=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8).read().decode()); m=d['metrics']; print(f'  requests_total={m[\"requests_total\"]}  writes_ok={m[\"writes_ok\"]}  auth_fails={m[\"auth_fails\"]}  rejected={m[\"rejected\"]}')"
echo.
echo === Last 12 lines tv_signals.jsonl ===
.venv\Scripts\python.exe -c "from pathlib import Path; lines=Path('logs/tv_signals.jsonl').read_text().splitlines(); [print(' ', l[:170]) for l in lines[-12:]]"
