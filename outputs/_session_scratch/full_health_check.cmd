@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo.
echo ============== 1. BRAIN ==============
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
powershell -NoProfile -Command "Get-Item 'logs\trend_master_brain.out' -ErrorAction SilentlyContinue | Select-Object Name, LastWriteTime, @{N='AgeMin';E={[math]::Round((Get-Date - $_.LastWriteTime).TotalMinutes,1)}} | Format-Table"

echo.
echo ============== 2. WEBHOOK + TUNNEL ==============
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='ngrok.exe'\" | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table"
.venv\Scripts\python.exe -c "import urllib.request as u, json; d=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8).read().decode()); m=d['metrics']; print(f'  PUBLIC URL  OK:  requests={m.get(\"requests_total\",0)}  writes_ok={m.get(\"writes_ok\",0)}  dryruns={m.get(\"dryruns\",0)}  rejected={m.get(\"rejected\",0)}  auth_fails={m.get(\"auth_fails\",0)}')"

echo.
echo ============== 3. MT5 ==============
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; ok=mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info() if ok else None; print(f'  MT5 init: {ok}'); pos=mt5.positions_get() or []; print(f'  positions={len(pos)}  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  margin=${ai.margin:.2f}'); [print(f'    {p.symbol} {(\"BUY\" if p.type==0 else \"SELL\")} pnl=${p.profit:.2f}') for p in pos]; mt5.shutdown()"

echo.
echo ============== 4. TELEGRAM NOTIFIER ==============
powershell -NoProfile -Command "Select-String -Path 'logs\trend_master_brain.out' -Pattern 'telegram_notifier:' -SimpleMatch | Select-Object -Last 3 | ForEach-Object { Write-Host '  ' $_.Line }"

echo.
echo ============== 5. TV ALERTS COUNT ==============
.venv\Scripts\python.exe -c "import json,time; from playwright.sync_api import sync_playwright; from pathlib import Path; PROFILE=Path('tools/tv_alert_setup/_browser_profile'); ROCKET='PUB;56f0fb74de7f4eed9325b987428b727e'; p=sync_playwright().start(); ctx=p.chromium.launch_persistent_context(user_data_dir=str(PROFILE.absolute()), headless=True); pg=ctx.pages[0] if ctx.pages else ctx.new_page(); pg.goto('https://www.tradingview.com/chart/', timeout=30000); time.sleep(3); r=ctx.request.post('https://pricealerts.tradingview.com/list_alerts', data=json.dumps({'payload':{'limit':5000}}), headers={'Origin':'https://www.tradingview.com','Referer':'https://www.tradingview.com/chart/','Content-Type':'application/json'}); a=r.json().get('r',[]); rp=[x for x in a if (x.get('condition') or {}).get('type')=='pine_alert' and ((x.get('condition') or {}).get('series') or [{}])[0].get('pine_id')==ROCKET]; act=sum(1 for x in rp if x.get('active')); print(f'  Total: {len(a)}  Rocket Prime: {len(rp)}  Active: {act}/{len(rp)}'); ctx.close(); p.stop()"

echo.
echo ============== 6. ZOMBIE / ORPHAN PROCESSES ==============
echo --- Playwright Chromium (any from tv_alert_setup):
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -match '_browser_profile' } | Measure-Object | Select-Object @{N='PlaywrightChromium';E={$_.Count}}"
echo --- Old python tv_alert procs (should be 0):
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_alert_setup*' } | Measure-Object | Select-Object @{N='ZombiePy';E={$_.Count}}"
echo --- Visible cmd/conhost from session:
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup|tm_launch|run_inspect|run_check|run_test|run_delete|run_quarantine|run_reset|run_api|run_create' } | Select-Object ProcessId, @{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length))}} | Format-Table"

echo.
echo ============== 7. RECENT TV SIGNALS (last 5) ==============
.venv\Scripts\python.exe -c "from pathlib import Path; from datetime import datetime; lines=Path('logs/tv_signals.jsonl').read_text().splitlines(); import json; [print(f'  {datetime.fromtimestamp(json.loads(l).get(\"ts\",0)).isoformat(timespec=\"seconds\")}  {json.loads(l).get(\"symbol\"):>7} {json.loads(l).get(\"direction\"):>4} src={json.loads(l).get(\"tv_strategy\")}') for l in lines[-5:]]"
