@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === FINAL STATE SNAPSHOT ===
echo.
echo --- 1. tools\tv_alert_setup\ contents (essentials only) ---
powershell -NoProfile -Command "Get-ChildItem 'tools\tv_alert_setup' | Where-Object { $_.Name -ne '_archive' -and $_.Name -ne '_browser_profile' -and $_.Name -ne '__pycache__' } | Sort-Object Name | Select-Object Name | Format-Table -HideTableHeaders"
echo.
echo --- 2. outputs\ contents ---
powershell -NoProfile -Command "Get-ChildItem 'outputs' | Sort-Object Name | Select-Object Name | Format-Table -HideTableHeaders"
echo.
echo --- 3. Workspace root cmd files ---
powershell -NoProfile -Command "Get-ChildItem '*.cmd' | Sort-Object Name | Select-Object Name, @{N='SizeKB';E={[math]::Round($_.Length/1024,1)}} | Format-Table -AutoSize"
echo.
echo --- 4. Active processes (final) ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'trend_master_brain|tv_webhook_receiver|tv_webhook_watchdog' } | Select-Object ProcessId, @{N='Type';E={if($_.CommandLine -like '*brain*'){'BRAIN'}elseif($_.CommandLine -like '*receiver*'){'WEBHOOK'}else{'WATCHDOG'}}}, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='ngrok.exe'\" | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table"
echo.
echo --- 5. EIA_API_KEY status (a known kami) ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); k=os.getenv('EIA_API_KEY','').strip(); print('  EIA_API_KEY:', 'SET' if k else 'MISSING (NG storage features auto-disabled)')"
echo.
echo --- 6. Account state ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  margin=${ai.margin:.2f}  positions={len(pos)}'); mt5.shutdown()"
echo.
echo --- 7. TV alerts state ---
.venv\Scripts\python.exe -c "import json,time; from playwright.sync_api import sync_playwright; from pathlib import Path; PROFILE=Path('tools/tv_alert_setup/_browser_profile').absolute(); ROCKET='PUB;56f0fb74de7f4eed9325b987428b727e'; p=sync_playwright().start(); ctx=p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True); pg=ctx.pages[0] if ctx.pages else ctx.new_page(); pg.goto('https://www.tradingview.com/chart/', timeout=30000); time.sleep(3); a=ctx.request.post('https://pricealerts.tradingview.com/list_alerts', data=json.dumps({'payload':{'limit':5000}}), headers={'Origin':'https://www.tradingview.com','Referer':'https://www.tradingview.com/chart/','Content-Type':'application/json'}).json().get('r',[]); rp=[x for x in a if (x.get('condition') or {}).get('type')=='pine_alert' and ((x.get('condition') or {}).get('series') or [{}])[0].get('pine_id')==ROCKET]; act=sum(1 for x in rp if x.get('active')); print(f'  Total alerts: {len(a)}  Rocket Prime: {len(rp)}  Active: {act}/{len(rp)}'); ctx.close(); p.stop()"
