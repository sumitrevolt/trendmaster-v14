@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe tools\tv_alert_setup\generate_alerts_format_b.py --symbols XAUUSD,EURUSD,USDJPY,GBPUSD,BTCUSD --timeframes M5,M15,M30,H1
echo.
echo === alerts_config.json sample (first 2 entries) ===
.venv\Scripts\python.exe -c "import json; d=json.load(open('tools/tv_alert_setup/alerts_config.json')); print(f'Total: {len(d)} alerts'); print(json.dumps(d[:2], indent=2))"
