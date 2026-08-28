@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Was BTCUSD body recorded in unparsed bodies log? ===
powershell -NoProfile -Command "if (Test-Path 'logs\tv_webhook_unparsed_bodies.log') { Get-Content 'logs\tv_webhook_unparsed_bodies.log' -Tail 25 } else { 'no file' }"
echo.
echo === Webhook log around 02:06 (BTCUSD time) ===
powershell -NoProfile -Command "Select-String -Path 'logs\tv_webhook.log' -Pattern '02:0[0-9]|BTCUSD' | Select-Object -Last 15 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === Confirm new alerts have plot-rich message field ===
.venv\Scripts\python.exe -c "import json,time; from playwright.sync_api import sync_playwright; from pathlib import Path; PROFILE=Path('tools/tv_alert_setup/_browser_profile').absolute(); ROCKET='PUB;56f0fb74de7f4eed9325b987428b727e'; p=sync_playwright().start(); ctx=p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True); pg=ctx.pages[0] if ctx.pages else ctx.new_page(); pg.goto('https://www.tradingview.com/chart/', timeout=30000); time.sleep(3); a=ctx.request.post('https://pricealerts.tradingview.com/list_alerts', data=json.dumps({'payload':{'limit':5000}}), headers={'Origin':'https://www.tradingview.com','Referer':'https://www.tradingview.com/chart/','Content-Type':'application/json'}).json().get('r',[]); rp=[x for x in a if (x.get('condition') or {}).get('type')=='pine_alert' and ((x.get('condition') or {}).get('series') or [{}])[0].get('pine_id')==ROCKET]; print(f'  Total RP alerts: {len(rp)}'); btc=[x for x in rp if 'BTC' in str(x.get('symbol',''))]; print(f'  BTC alerts: {len(btc)}'); print(f'  BTC sample message: {btc[0].get(\"message\",\"empty\")[:200] if btc else \"none\"}'); print(); print(f'  Active count: {sum(1 for x in rp if x.get(\"active\"))}/{len(rp)}'); plot_msgs=sum(1 for x in rp if 'plot_' in str(x.get('message',''))); print(f'  Alerts with plot placeholders in message: {plot_msgs}/{len(rp)}'); ctx.close(); p.stop()"
echo.
echo === Last 6 webhook log lines ===
powershell -NoProfile -Command "Get-Content 'logs\tv_webhook.log' -Tail 8"
