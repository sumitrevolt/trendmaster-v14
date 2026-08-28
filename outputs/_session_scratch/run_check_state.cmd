@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === ALERTS state ===
.venv\Scripts\python.exe outputs\check_alert_state.py
echo.
echo === Recent webhook signals (last 15 lines) ===
.venv\Scripts\python.exe -c "from pathlib import Path; lines=Path('logs/tv_signals.jsonl').read_text().splitlines(); [print(l[:180]) for l in lines[-15:]]"
echo.
echo === Webhook stats now ===
.venv\Scripts\python.exe -c "import urllib.request as u, json; d=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8).read().decode()); m=d['metrics']; print(f'  requests={m[\"requests_total\"]}  writes_ok={m[\"writes_ok\"]}  rejected={m[\"rejected\"]}  auth_fails={m[\"auth_fails\"]}')"
echo.
echo === Brain trade activity (last 30 lines from brain log) ===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\trend_master_brain.out' -Tail 30 -ErrorAction SilentlyContinue"
