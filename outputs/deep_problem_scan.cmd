@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============== DEEP PROBLEM SCAN ==============
echo.
echo --- 1. Errors/exceptions in last 6 hours of brain log ---
powershell -NoProfile -Command "$cutoff=(Get-Date).AddHours(-6); (Select-String -Path 'logs\trend_master_brain.out' -Pattern 'ERROR|FATAL|Traceback' -ErrorAction SilentlyContinue | Select-Object -Last 5 | ForEach-Object { '  ' + $_.Line.Substring(0, [Math]::Min(180, $_.Line.Length)) })"
echo.
echo --- 2. Errors in webhook log ---
powershell -NoProfile -Command "Select-String -Path 'logs\tv_webhook.log' -Pattern 'ERROR|FATAL|Traceback|Exception' | Select-Object -Last 5 | ForEach-Object { '  ' + $_.Line.Substring(0, [Math]::Min(180, $_.Line.Length)) }"
echo.
echo --- 3. Errors in executor log ---
powershell -NoProfile -Command "Select-String -Path 'logs\python_executor.log' -Pattern 'ERROR|FATAL|Traceback' | Select-Object -Last 5 | ForEach-Object { '  ' + $_.Line.Substring(0, [Math]::Min(180, $_.Line.Length)) }"
echo.
echo --- 4. Disk usage of logs/ folder ---
powershell -NoProfile -Command "$total=(Get-ChildItem 'logs' -Recurse -File | Measure-Object Length -Sum).Sum; Write-Host ('  total: {0:N1} MB' -f ($total/1MB)); Get-ChildItem 'logs' -File | Sort-Object Length -Descending | Select-Object -First 5 | ForEach-Object { Write-Host ('  ' + $_.Name + ': {0:N1} MB' -f ($_.Length/1MB)) }"
echo.
echo --- 5. Stale signal files in MT5 dir ---
powershell -NoProfile -Command "$f='C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files'; Get-ChildItem $f -Filter 'trendmaster_signals*.json' -ErrorAction SilentlyContinue | Select-Object Name, LastWriteTime, @{N='AgeMin';E={[math]::Round((Get-Date - $_.LastWriteTime).TotalMinutes,1)}} | Sort-Object AgeMin | Format-Table -AutoSize"
echo.
echo --- 6. News calendar freshness ---
powershell -NoProfile -Command "$f='config\news_calendar.json'; if (Test-Path $f) { $age=[math]::Round(((Get-Date)-(Get-Item $f).LastWriteTime).TotalDays,1); Write-Host ('  age: ' + $age + ' days  ' + (if($age -gt 7){'STALE - refresh needed'}else{'fresh OK'}))}"
echo.
echo --- 7. Brain shadow predictions writing? ---
powershell -NoProfile -Command "$f='logs\brain_shadow_predictions.jsonl'; if (Test-Path $f) { $age=[math]::Round(((Get-Date)-(Get-Item $f).LastWriteTime).TotalMinutes,1); Write-Host ('  last write: ' + $age + ' min ago  size: {0:N1} MB' -f ((Get-Item $f).Length/1MB)) }"
echo.
echo --- 8. Telegram notifier last activity ---
powershell -NoProfile -Command "(Select-String -Path 'logs\trend_master_brain.out' -Pattern 'telegram_notifier|tg_send' -ErrorAction SilentlyContinue | Select-Object -Last 3 | ForEach-Object { '  ' + $_.Line.Substring(0, [Math]::Min(150, $_.Line.Length)) })"
echo.
echo --- 9. Zombie process check ---
powershell -NoProfile -Command "$cmds=(Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup|tm_launch|run_inspect|run_check|run_reactivate|verify_plot' }).Count; Write-Host ('  leftover cmd shells: ' + $cmds)"
powershell -NoProfile -Command "$chrome=(Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*_browser_profile*' }).Count; Write-Host ('  Playwright Chromium procs: ' + $chrome)"
echo.
echo --- 10. EA / safeguards last block ---
powershell -NoProfile -Command "Select-String -Path 'logs\python_executor.log' -Pattern 'SAFEGUARD BLOCK|skip ' | Select-Object -Last 5 | ForEach-Object { '  ' + $_.Line.Substring(0, [Math]::Min(160, $_.Line.Length)) }"
echo.
echo --- 11. Recent (last 30 min) tv_signals events ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json, time; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; cutoff=time.time()-1800; recent=[r for r in lines if r.get('ts',0)>cutoff]; print(f'  count last 30 min: {len(recent)}'); [print(f'    {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\")} {r.get(\"event\",\"?\"):<20} {r.get(\"symbol\",\"-\"):8} dir={r.get(\"direction\",\"-\"):4} src={r.get(\"tv_strategy\",\"?\")[:25]}') for r in recent[-5:]]"
echo.
echo --- 12. brain_state.json key fields sanity ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; s=json.loads(Path('logs/brain_state.json').read_text()); print(f'  trading_paused: {s.get(\"trading_paused\")}'); print(f'  drawdown_lockout: {datetime.fromtimestamp(s.get(\"drawdown_lockout_until\",0)).isoformat() if s.get(\"drawdown_lockout_until\",0)>0 else \"none\"}'); print(f'  start_of_day_equity: {s.get(\"start_of_day_equity\")}'); print(f'  recent_results count: {len(s.get(\"recent_results\",[]))}')"
