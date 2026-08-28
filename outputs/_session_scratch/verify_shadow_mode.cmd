@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === 1. Local webhook health (bypass tunnel) ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:5005/health', timeout=5); print('  LOCAL HTTP', r.status, r.read().decode()[:120])"
echo.
echo === 2. ngrok tunnel binary check ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='ngrok.exe'\" | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='cloudflared.exe'\" | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
echo.
echo === 3. Tunnel public health ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=8); print('  PUBLIC HTTP', r.status, r.read().decode()[:120])" 2>&1 | findstr /v Traceback
echo.
echo === 4. Brain shadow mode verification — check if brain wrote to trade signal files ===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals*.json' -ErrorAction SilentlyContinue | Select-Object Name, LastWriteTime | Format-Table -AutoSize"
echo.
echo === 5. brain_shadow_predictions.jsonl (where shadow brain writes) ===
powershell -NoProfile -Command "if (Test-Path 'C:\Users\Ratanshila\Documents\autmated trading\logs\brain_shadow_predictions.jsonl') { Get-Item 'C:\Users\Ratanshila\Documents\autmated trading\logs\brain_shadow_predictions.jsonl' | Select-Object Name, LastWriteTime, Length | Format-Table; Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\brain_shadow_predictions.jsonl' -Tail 3 } else { Write-Host '  (file does not exist yet)' }"
echo.
echo === 6. TV alerts state (verify still active after restart) ===
.venv\Scripts\python.exe -c "import json,time; from playwright.sync_api import sync_playwright; from pathlib import Path; PROFILE=Path(r'C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup\_browser_profile'); ROCKET='PUB;56f0fb74de7f4eed9325b987428b727e'; p=sync_playwright().start(); ctx=p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True); pg=ctx.pages[0] if ctx.pages else ctx.new_page(); pg.goto('https://www.tradingview.com/chart/', wait_until='domcontentloaded', timeout=30000); time.sleep(3); r=ctx.request.post('https://pricealerts.tradingview.com/list_alerts', data=json.dumps({'payload':{'limit':5000}}), headers={'Origin':'https://www.tradingview.com','Referer':'https://www.tradingview.com/chart/','Content-Type':'application/json'}, timeout=15000); alerts=r.json().get('r',[]); rp=[(json.loads(a['symbol'][1:]).get('symbol') if a['symbol'].startswith('=') else a['symbol'], a.get('resolution'), a.get('active')) for a in alerts if (a.get('condition') or {}).get('type')=='pine_alert' and ((a.get('condition') or {}).get('series') or [{}])[0].get('pine_id')==ROCKET]; rp.sort(); print(f'  Total Rocket Prime alerts: {len(rp)}'); print(f'  Active: {sum(1 for x in rp if x[2])}'); ctx.close(); p.stop()"
