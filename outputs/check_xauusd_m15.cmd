@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === XAUUSD signals in tv_signals.jsonl (with TF) ===
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; xau=[r for r in lines if r.get('symbol')=='XAUUSD']; print(f'Total XAUUSD events: {len(xau)}'); [print(f'  {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\"):>10}  event={r.get(\"event\",\"?\"):<14} dir={r.get(\"direction\",\"-\"):<5} tf={r.get(\"tv_timeframe\",\"-\"):<4} src={r.get(\"tv_strategy\",\"?\")[:25]}') for r in xau[-15:]]"
echo.
echo === MT5 file for XAUUSD (latest signal) ===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals*.json' | Where-Object { $_.Name -match 'XAUUSD|signals\.json$' } | Sort-Object LastWriteTime -Descending | Select-Object -First 3 | Select-Object Name, LastWriteTime, @{N='AgeMin';E={[math]::Round((Get-Date - $_.LastWriteTime).TotalMinutes,1)}} | Format-Table"
echo.
echo === Last 15 lines executor log (look for XAUUSD entries) ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 50 | Select-String 'XAUUSD' | Select-Object -Last 10 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === Read content of XAUUSD signal file ===
powershell -NoProfile -Command "if (Test-Path 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals.json') { Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals.json' }"
