@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============== POST-CHANGE HEALTH CHECK ==============
echo.
echo --- 1. Skills count ---
powershell -NoProfile -Command "$d='docs\skills'; $active=(Get-ChildItem $d -Directory | Where-Object { -not $_.Name.StartsWith('_') }).Count; $arch=(Get-ChildItem '$d\_archive_2026-05-06' -Directory -ErrorAction SilentlyContinue).Count; '  active: ' + $active + '  archived: ' + $arch"
echo.
echo --- 2. New skills present ---
powershell -NoProfile -Command "@('trading-tv-signal-quality','trading-position-sizing-volatility','trading-shadow-validation') | ForEach-Object { $p='docs\skills\'+$_+'\SKILL.md'; if (Test-Path $p) { '  OK ' + $_ } else { '  MISSING ' + $_ } }"
echo.
echo --- 3. Stale skills gone ---
powershell -NoProfile -Command "@('trading-alert-bridge','trading-events-rotator','trading-next-prompt') | ForEach-Object { $p='docs\skills\'+$_; if (Test-Path $p) { '  STILL HERE ' + $_ } else { '  GONE ' + $_ } }"
echo.
echo --- 4. Brain alive ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Measure-Object | Select-Object @{N='BrainProcs';E={$_.Count}}"
echo.
echo --- 5. Webhook + ngrok ---
.venv\Scripts\python.exe -c "import urllib.request as u, json; r=json.loads(u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8).read().decode()); m=r['metrics']; print(f'  webhook OK: writes={m[\"writes_ok\"]}  rejected={m[\"rejected\"]}  dryruns={m.get(\"dryruns\",0)}  auth_fails={m[\"auth_fails\"]}')"
echo.
echo --- 6. MT5 + positions ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  positions={len(pos)}'); [print(f'    {p.symbol} {(\"BUY\" if p.type==0 else \"SELL\")} pnl=${p.profit:.2f}') for p in pos]; mt5.shutdown()"
echo.
echo --- 7. Code-review-graph health ---
powershell -NoProfile -Command "if (Test-Path '.code-review-graph\graph.db') { $g=Get-Item '.code-review-graph\graph.db'; '  graph.db: ' + [math]::Round($g.Length/1024/1024,1) + ' MB  updated: ' + $g.LastWriteTime }"
echo.
echo --- 8. Pre-commit guard test ---
.venv\Scripts\python.exe tools\check_no_resolve.py
echo.
echo --- 9. Active scheduled tasks count ---
schtasks /Query /FO TABLE | findstr /i "TrendMaster" | findstr /v "Disabled" | find /c /v ""
echo.
echo --- 10. tv_executor gates intact ---
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_executor.py' -Pattern 'gate_block_news|gate_block_dd|gate_block_corr' -SimpleMatch | Measure-Object | Select-Object @{N='GateRefs';E={$_.Count}}"
