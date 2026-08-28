@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============== FINAL HEALTH CHECK ==============
echo.
echo --- Processes ---
powershell -NoProfile -Command "$brain=(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' }).Count; $webhook=(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' }).Count; $ngrok=(Get-CimInstance Win32_Process -Filter \"name='ngrok.exe'\").Count; $exec=(Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' }).Count; Write-Host ('  brain:    ' + $brain + ' procs'); Write-Host ('  webhook:  ' + $webhook + ' procs'); Write-Host ('  ngrok:    ' + $ngrok + ' procs'); Write-Host ('  executor: ' + $exec + ' procs')"
echo.
echo --- Webhook public health ---
.venv\Scripts\python.exe -c "import urllib.request as u, json; d=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=5).read().decode()); m=d['metrics']; print(f'  HTTP 200 reachable, requests={m[\"requests_total\"]} writes_ok={m[\"writes_ok\"]} rejected={m[\"rejected\"]} dryruns={m.get(\"dryruns\",0)}')"
echo.
echo --- MT5 + positions ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  margin=${ai.margin:.2f}  positions={len(pos)}'); [print(f'    {p.symbol} {(\"BUY\" if p.type==0 else \"SELL\"):4} pnl=${p.profit:.2f}  open={p.price_open:.2f}  cur={p.price_current:.2f}') for p in pos]; mt5.shutdown()"
echo.
echo --- TV alerts state ---
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=5); print('  webhook reachable:', r.status)"
echo.
echo --- Last 3 webhook signal events ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; [print(f'  {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\")} {r.get(\"event\"):<14} {r.get(\"symbol\",\"-\"):8} {r.get(\"direction\",\"-\"):4} src={r.get(\"tv_strategy\",\"?\")}') for r in lines[-3:]]"
echo.
echo --- Active scheduled tasks ---
schtasks /Query /FO TABLE 2>nul | findstr /i "TrendMaster" | findstr /v "Disabled" | find /c /v ""
echo.
echo --- Brain log freshness ---
powershell -NoProfile -Command "$f='logs\trend_master_brain.out'; if (Test-Path $f) { $age=[math]::Round(((Get-Date)-(Get-Item $f).LastWriteTime).TotalMinutes,1); Write-Host ('  brain.out last write: ' + $age + ' min ago') }"
echo.
echo --- Recent error/warning count last hour ---
powershell -NoProfile -Command "$cutoff=(Get-Date).AddHours(-1); $errs=(Select-String -Path 'logs\trend_master_brain.out' -Pattern 'ERROR|FATAL|Traceback' -ErrorAction SilentlyContinue | Where-Object { try { ([DateTime]::Parse($_.Line.Substring(0,19))) -gt $cutoff } catch { $false } }).Count; Write-Host ('  brain errors last hour: ' + $errs)"
echo.
echo --- Plot values diagnostic log ---
powershell -NoProfile -Command "$f='logs\tv_plot_values.jsonl'; if (Test-Path $f) { Write-Host ('  exists, ' + (Get-Item $f).Length + ' bytes, ' + (Get-Content $f).Count + ' entries') } else { Write-Host '  not yet (will populate on first real signal)' }"
