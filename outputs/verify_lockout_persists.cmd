@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Wait 30 sec for brain to re-read state ===
ping 127.0.0.1 -n 31 >nul
echo.
echo === Check if brain re-saved old lockout (regression) ===
.venv\Scripts\python.exe -c "from pathlib import Path; import json; s=json.loads(Path('logs/brain_state.json').read_text()); print(f'  drawdown_lockout_until: {s.get(\"drawdown_lockout_until\")}'); print(f'  cooldown_until_ts:      {s.get(\"cooldown_until_ts\")}'); print(f'  trading_paused:         {s.get(\"trading_paused\")}'); print(f'  last_saved_at:          {s.get(\"last_saved_at\")}')"
echo.
echo === Brain log — any lockout writes? ===
powershell -NoProfile -Command "Select-String -Path 'logs\trend_master_brain.out' -Pattern 'drawdown|lockout|halt' | Select-Object -Last 10 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === Check brain process still alive ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Measure-Object | Select-Object @{N='BrainProcs';E={$_.Count}}"
echo.
echo === Trigger Test alert manually OR wait for next real fire ===
echo (Open TV, right-click any of 20 alerts, click 'Test alert')
