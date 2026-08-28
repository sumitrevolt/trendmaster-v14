@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Webhook health ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  ', r.status, r.read().decode()[:120])"
echo.
echo === All 3 priority blocks in receiver ===
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_webhook_receiver.py' -Pattern 'rocket_prime_plot0|rocket_prime_url_direction|rocket_prime_inferred' | Select-Object -Last 6 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === TV alert state (count + active) ===
.venv\Scripts\python.exe outputs\verify_alerts_simple.py
echo.
echo === Sample alert message check ===
.venv\Scripts\python.exe -c "import json,time; from playwright.sync_api import sync_playwright; from pathlib import Path; PROFILE=Path('tools/tv_alert_setup/_browser_profile').absolute(); ROCKET='PUB;56f0fb74de7f4eed9325b987428b727e'; p=sync_playwright().start(); ctx=p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True); pg=ctx.pages[0] if ctx.pages else ctx.new_page(); pg.goto('https://www.tradingview.com/chart/', timeout=30000); time.sleep(3); a=ctx.request.post('https://pricealerts.tradingview.com/list_alerts', data=json.dumps({'payload':{'limit':5000}}), headers={'Origin':'https://www.tradingview.com','Referer':'https://www.tradingview.com/chart/','Content-Type':'application/json'}).json().get('r',[]); rp=[x for x in a if (x.get('condition') or {}).get('type')=='pine_alert' and ((x.get('condition') or {}).get('series') or [{}])[0].get('pine_id')==ROCKET]; print(f'  Total RP alerts: {len(rp)}'); [print(f'  Sample message: {x.get(\"message\")[:200] if x.get(\"message\") else \"(empty)\"}') for x in rp[:1]]; ctx.close(); p.stop()"
