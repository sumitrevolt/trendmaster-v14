@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === STEP 1: Clear lockout in state file ===
.venv\Scripts\python.exe outputs\clear_dd_lockout.py
echo.
echo === STEP 2: Surgical restart brain (so in-memory state matches disk) ===
call start_brain_clean.cmd
echo.
echo === STEP 3: Wait 20 sec for brain to settle ===
ping 127.0.0.1 -n 21 >nul
echo.
echo === STEP 4: Verify lockout REMAINS cleared ===
.venv\Scripts\python.exe -c "from pathlib import Path; import json; s=json.loads(Path('logs/brain_state.json').read_text()); lk=s.get('drawdown_lockout_until'); print(f'  drawdown_lockout_until: {lk}'); print('  STATUS:', 'CLEARED OK' if lk == 0 else 'STILL SET (regression)')"
echo.
echo === STEP 5: Brain alive? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Measure-Object | Select-Object @{N='BrainProcs';E={$_.Count}}"
echo.
echo === STEP 6: Webhook still alive (surgical kill should NOT have touched it) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | Measure-Object | Select-Object @{N='WebhookProcs';E={$_.Count}}"
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  Public health:', r.status)"
