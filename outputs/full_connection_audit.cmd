@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo ============== FULL CONNECTION AUDIT ==============
echo.

echo --- 1. MT5 (broker connection) ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; ok=mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ti=mt5.terminal_info() if ok else None; ai=mt5.account_info() if ok else None; print(f'  init={ok}  trade_allowed={ti.trade_allowed if ti else None}  connected={ti.connected if ti else None}  balance=${ai.balance:.2f}' if ti and ai else f'  init={ok}'); mt5.shutdown()"
echo.

echo --- 2. TV ngrok tunnel public health ---
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  HTTP', r.status, r.read().decode()[:80])"
echo.

echo --- 3. Local webhook receiver health ---
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:5005/health', timeout=3); print('  HTTP', r.status)"
echo.

echo --- 4. Telegram bot reachability ---
.venv\Scripts\python.exe -c "import os, urllib.request as u, json; from dotenv import load_dotenv; load_dotenv('config/.env'); bot=os.getenv('TELEGRAM_BOT_TOKEN'); r=u.urlopen(f'https://api.telegram.org/bot{bot}/getMe', timeout=5); d=json.loads(r.read().decode()); print('  bot=' + (d.get('result',{}).get('username') if d.get('ok') else 'FAIL'))"
echo.

echo --- 5. TradingView API (auth via Playwright cookie) ---
.venv\Scripts\python.exe -c "import json, time; from playwright.sync_api import sync_playwright; from pathlib import Path; PROFILE=Path('tools/tv_alert_setup/_browser_profile').absolute(); p=sync_playwright().start(); ctx=p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True); pg=ctx.pages[0] if ctx.pages else ctx.new_page(); pg.goto('https://www.tradingview.com/chart/', timeout=20000); time.sleep(2); cookies=ctx.cookies(); has_session=any(c['name'] in ('sessionid','sessionid_sign','tv_ecuid') for c in cookies); print('  TV session cookie:', 'PRESENT' if has_session else 'MISSING'); ctx.close(); p.stop()" 2>&1 | findstr /v "Traceback File"
echo.

echo --- 6. Code-review-graph ---
.venv\Scripts\python.exe -c "from pathlib import Path; p=Path('.code-review-graph/graph.db'); print('  graph.db:', f'{p.stat().st_size/1024/1024:.1f} MB' if p.exists() else 'MISSING')"
echo.

echo --- 6b. CRG hook in .claude/settings.json? ---
powershell -NoProfile -Command "if (Test-Path '.claude\settings.json') { $j=Get-Content '.claude\settings.json' -Raw; if ($j -match 'crg_hook|code.review.graph') { '  hook configured: YES' } else { '  hook configured: NO' } } else { '  no .claude/settings.json' }"
echo.

echo --- 7. EIA API key ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); k=os.getenv('EIA_API_KEY','').strip(); print('  EIA_API_KEY:', 'SET' if k else 'MISSING')"
echo.

echo --- 8. News calendar freshness ---
.venv\Scripts\python.exe -c "from pathlib import Path; from datetime import datetime; p=Path('config/news_calendar.json'); age_days=(datetime.now().timestamp() - p.stat().st_mtime)/86400 if p.exists() else None; print(f'  age: {age_days:.1f} days  ({\"STALE — refresh\" if age_days and age_days>7 else \"fresh OK\" if age_days else \"missing\"})')"
echo.

echo --- 9. Brain MT5 connection (alive heartbeat) ---
powershell -NoProfile -Command "$ok=Select-String -Path 'logs\trend_master_brain.out' -Pattern 'MT5 connected|trade_master|tick_all summary' | Select-Object -Last 1; if ($ok) { '  last brain MT5 activity: ' + $ok.Line.Substring(0, [Math]::Min(140, $ok.Line.Length)) } else { '  no recent brain activity' }"
echo.

echo --- 10. Executor MT5 connection ---
powershell -NoProfile -Command "$last=Select-String -Path 'logs\python_executor.log' -Pattern 'MT5 connected' | Select-Object -Last 1; if ($last) { '  ' + $last.Line.Substring(0, [Math]::Min(140, $last.Line.Length)) }"
echo.

echo --- 11. Pre-commit hooks ---
powershell -NoProfile -Command "if (Test-Path '.git\hooks\pre-commit') { '  pre-commit hook: PRESENT' } else { '  pre-commit hook: MISSING' }; if (Test-Path '.git\hooks\post-commit') { '  post-commit hook: PRESENT' } else { '  post-commit hook: MISSING' }"
echo.

echo --- 12. Junction state ---
powershell -NoProfile -Command "$j=Get-Item 'ai_trading_agents' -ErrorAction SilentlyContinue; if ($j -and $j.LinkType -eq 'Junction') { '  ai_trading_agents -> ' + $j.Target } else { '  JUNCTION MISSING/BROKEN' }"
echo.

echo --- 13. tv_executor signal write target ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); p=os.getenv('MT5_FILES_DIR','').strip(); from pathlib import Path; print(f'  MT5_FILES_DIR: {p}'); print(f'  exists: {Path(p).exists() if p else False}')"
echo.

echo --- 14. Dashboard reachability + lock ---
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('http://localhost:8765', timeout=3); print('  HTTP', r.status)"
powershell -NoProfile -Command "if (Test-Path 'logs\dashboard_server.lock') { 'lock present' } else { 'no lock' }"
echo.

echo --- 15. Scheduled tasks active count ---
schtasks /Query /FO TABLE 2>nul | findstr /i "TrendMaster" | findstr /v "Disabled" | find /c /v ""
echo.

echo --- 16. Cloudflare backup tunnel exists? ---
powershell -NoProfile -Command "if (Test-Path 'tools\cloudflared.exe') { '  cloudflared.exe: present (backup tunnel option)' } else { '  cloudflared.exe: MISSING (no backup tunnel)' }"
echo.

echo --- 17. ngrok config / token ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); print('  TUNNEL_MODE:', os.getenv('TUNNEL_MODE','?')); print('  NGROK_DOMAIN:', os.getenv('NGROK_DOMAIN','?')); print('  TV_PUBLIC_URL:', os.getenv('TV_PUBLIC_URL','?'))"
echo.

echo --- 18. Pair toggles all enabled? ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; cfg=json.loads(Path('logs/dashboard_config.json').read_text()) if Path('logs/dashboard_config.json').exists() else {}; pe=cfg.get('pairs_enabled',{}); te=cfg.get('trading_enabled', True); print(f'  trading_enabled: {te}'); print(f'  pairs_enabled: {sum(1 for v in pe.values() if v)}/{len(pe)} on  ({list(k for k,v in pe.items() if not v) or \"all on\"})')" 2>&1 | findstr /v Traceback
