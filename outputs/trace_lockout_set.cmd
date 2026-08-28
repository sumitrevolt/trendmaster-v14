@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Brain log AFTER restart (last 50 lines) ===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 50"
echo.
echo === Search for veto/lockout messages ===
powershell -NoProfile -Command "Select-String -Path 'logs\trend_master_brain.out' -Pattern 'daily_dd|lockout|profit_gate veto|DRAWDOWN' | Select-Object -Last 15 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === PROFIT_OPTIMIZER intraday_dd_pct ===
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from config.settings import PROFIT_OPTIMIZER; print('  intraday_dd_pct:', PROFIT_OPTIMIZER.get('intraday_dd_pct')); print('  daily_max_loss_pct:', PROFIT_OPTIMIZER.get('daily_max_loss_pct'))"
echo.
echo === Current state file lockout value ===
.venv\Scripts\python.exe -c "from pathlib import Path; import json; s=json.loads(Path('logs/brain_state.json').read_text()); print(f'  lockout: {s.get(\"drawdown_lockout_until\")}'); print(f'  daily_drawdown_peak_eq: {s.get(\"daily_drawdown_peak_eq\")}'); print(f'  start_of_day_equity: {s.get(\"start_of_day_equity\")}'); print(f'  last_saved_at: {s.get(\"last_saved_at\")}')"
