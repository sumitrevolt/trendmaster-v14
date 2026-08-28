@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === RECENT TV SIGNALS (last 25) ===
.venv\Scripts\python.exe -c "from pathlib import Path; lines=[l for l in Path('logs/tv_signals.jsonl').read_text(encoding='utf-8',errors='replace').splitlines() if l.strip()]; [print(l) for l in lines[-25:]]"
echo.
echo === RECENT EXECUTOR LOG (last 80 lines) ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 80"
echo.
echo === EXECUTOR SAFEGUARD/SKIP HITS (last 24h) ===
powershell -NoProfile -Command "if (Test-Path 'logs\python_executor.log') { Get-Content 'logs\python_executor.log' | Select-String -Pattern 'SAFEGUARD BLOCK|skip |REJECT|ORDER FAIL|order_send|retcode' | Select-Object -Last 30 }"
echo.
echo === CURRENT MT5 POSITIONS + CONCENTRATION ===
.venv\Scripts\python.exe outputs\check_concentration.py
echo.
echo === RECENT PLOT VALUES (direction extraction working?) ===
powershell -NoProfile -Command "if (Test-Path 'logs\tv_plot_values.jsonl') { Get-Content 'logs\tv_plot_values.jsonl' -Tail 15 } else { echo '  (no plot values logged)' }"
echo.
echo === EXECUTOR ALIVE? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Select-Object ProcessId, @{N='AgeMin';E={[math]::Round((New-TimeSpan -Start $_.CreationDate -End (Get-Date)).TotalMinutes,1)}} | Format-Table"
echo.
echo === MT5 SIGNAL FILE TIMESTAMPS ===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\*\MQL5\Files\AI_Bridge_*.json' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object Name, @{N='AgeMin';E={[math]::Round((New-TimeSpan -Start $_.LastWriteTime -End (Get-Date)).TotalMinutes,1)}} | Select-Object -First 8 | Format-Table"
echo.
echo === WEBHOOK RECENT ACTIVITY ===
powershell -NoProfile -Command "if (Test-Path 'logs\tv_webhook.log') { Get-Content 'logs\tv_webhook.log' -Tail 40 }"
