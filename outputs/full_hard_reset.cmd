@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === STEP 1: Hard reset state ===
.venv\Scripts\python.exe outputs\hard_reset_dd.py
echo.
echo === STEP 2: Surgical brain restart ===
call start_brain_clean.cmd
echo.
echo === STEP 3: Wait 25 sec ===
ping 127.0.0.1 -n 26 >nul
echo.
echo === STEP 4: Verify lockout STAYS cleared ===
.venv\Scripts\python.exe -c "from pathlib import Path; import json; s=json.loads(Path('logs/brain_state.json').read_text()); lk=s.get('drawdown_lockout_until'); print(f'  drawdown_lockout_until: {lk}'); print(f'  start_of_day_equity:    {s.get(\"start_of_day_equity\")}'); print(f'  recent_results count:   {len(s.get(\"recent_results\", []))}'); print('  STATUS:', 'CLEARED OK' if lk == 0 else 'STILL SET (bad)')"
