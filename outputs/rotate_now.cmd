@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Run rotation with patched script (now handles .jsonl) ===
.venv\Scripts\python.exe tools\daily_maintenance.py
echo.
echo === Logs after rotation ===
powershell -NoProfile -Command "$total=(Get-ChildItem 'logs' -Recurse -File | Measure-Object Length -Sum).Sum; Write-Host ('  Total logs: {0:N1} MB' -f ($total/1MB)); Get-ChildItem 'logs' -File | Sort-Object Length -Descending | Select-Object -First 6 | ForEach-Object { Write-Host ('  ' + $_.Name + ': {0:N1} MB' -f ($_.Length/1MB)) }"
echo.
echo === MT5 state - URGENT P/L check ===
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  margin=${ai.margin:.2f}'); print(f'  floating P/L: ${ai.equity - ai.balance:+.2f}'); print(f'  DD %: {((ai.balance - ai.equity) / ai.balance * 100):+.2f}%' if ai.balance else 'N/A'); print('  POSITIONS:'); [print(f'    {p.symbol} {(\"BUY\" if p.type==0 else \"SELL\"):4} pnl=${p.profit:+.2f}  open={p.price_open:.2f}  cur={p.price_current:.2f}') for p in pos]; mt5.shutdown()"
