@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ========== A. RISK / SAFETY GAPS ==========
echo.
echo --- A1. Correlation guard? (e.g. XAU+XAG both fire = same trade twice) ---
.venv\Scripts\python.exe -c "from pathlib import Path; t=Path('ai_trading_agents/rolling_corr.py').exists(); print('  rolling_corr.py exists:', t); import re; s=Path('ai_trading_agents/tv_executor.py').read_text(); print('  tv_executor uses correlation gate:', 'correlation' in s.lower() or 'rolling_corr' in s.lower())"
echo.
echo --- A2. Does TV-signal path respect news blackout? ---
.venv\Scripts\python.exe -c "from pathlib import Path; s=Path('ai_trading_agents/tv_executor.py').read_text(); print('  tv_executor calls news_feed:', 'news' in s.lower()); print('  tv_executor calls profit_filters:', 'profit_filter' in s.lower())"
echo.
echo --- A3. Daily $-loss cap for TV signals? ---
.venv\Scripts\python.exe -c "from pathlib import Path; s=Path('ai_trading_agents/tv_executor.py').read_text(); print('  tv_executor checks daily_loss_limit:', 'daily_loss' in s.lower() or 'max_daily_drawdown' in s.lower())"
echo.
echo --- A4. Watchpet for brain death alert? ---
.venv\Scripts\python.exe -c "from pathlib import Path; import os; ws=list(Path('tools').glob('watchpet*')); ws+=list(Path('tools').glob('*alive*')); ws+=list(Path('tools').glob('*health*')); [print(f'  found:', w.name) for w in ws]; print('  scheduled task TrendMaster_BrainAlive?'); os.system('schtasks /Query /TN \"TrendMaster Brain Watchdog\" 1>nul 2>&1 && echo   YES installed || echo   NOT installed')"
echo.
echo ========== B. ALPHA / SIGNAL QUALITY GAPS ==========
echo.
echo --- B1. Meta-label gates state ---
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from config.settings import LIVE_BRAIN; print('  metalabel_enabled:', LIVE_BRAIN.get('metalabel_enabled')); print('  metalabel_perteam_enabled:', LIVE_BRAIN.get('metalabel_perteam_enabled')); print('  smartmoney_features_enabled:', LIVE_BRAIN.get('smartmoney_features_enabled'))"
echo.
echo --- B2. Recent shadow predictions count + latency ---
powershell -NoProfile -Command "$f='logs/brain_shadow_predictions.jsonl'; if (Test-Path $f) { $size=(Get-Item $f).Length/1MB; $lines=(Get-Content $f).Count; Write-Host '  size:' ([math]::Round($size,1)) 'MB  lines:' $lines }"
echo.
echo --- B3. tf=- bug in real signals (receiver not parsing URL ?tf= for plain-text) ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; lines=Path('logs/tv_signals.jsonl').read_text().splitlines(); recent=[json.loads(l) for l in lines[-15:]]; counts={}; [counts.update({(r.get('tv_strategy','?'), r.get('tv_timeframe') or '-'): counts.get((r.get('tv_strategy','?'), r.get('tv_timeframe') or '-'), 0) + 1}) for r in recent]; [print(f'  src={s:<22} tf={t:<5}  count={c}') for (s,t), c in counts.items()]"
echo.
echo ========== C. OBSERVABILITY GAPS ==========
echo --- C1. Dashboard running on :8765? ---
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('http://localhost:8765', timeout=3); print('  HTTP', r.status)" 2>nul || echo   NOT running
echo.
echo --- C2. Daily digest scheduled task? ---
schtasks /Query /TN "TrendMaster Daily Digest" 1>nul 2>&1 && echo   YES installed || echo   NOT installed
echo.
echo --- C3. tv_webhook_watchdog running? ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_watchdog*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_watchdog*' } | Select-Object ProcessId | Format-Table"
echo.
echo ========== D. BACKUP / DR GAPS ==========
echo.
echo --- D1. Backup of critical recreate-data files ---
.venv\Scripts\python.exe -c "from pathlib import Path; import shutil, datetime as dt; base=Path('tools/tv_alert_setup'); critical=['pine_alert_template.json', 'capture_create_post.json']; [print(f'  {f}: exists={(base/f).exists()}, size={(base/f).stat().st_size if (base/f).exists() else 0}b') for f in critical]"
echo.
echo --- D2. Last brain_state.json backup? ---
powershell -NoProfile -Command "Get-ChildItem 'logs/brain_state*' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | Select-Object Name, LastWriteTime, @{N='SizeKB';E={[math]::Round($_.Length/1024,1)}} | Format-Table"
echo.
echo ========== E. CODE / TECH DEBT ==========
echo.
echo --- E1. .resolve() trap regressions in brain package ---
powershell -NoProfile -Command "(Select-String -Path 'C:\TrendMaster_aita_canonical\*.py' -Pattern '.resolve()' -SimpleMatch -ErrorAction SilentlyContinue | Measure-Object).Count" 
echo   (^ if non-zero, that many .resolve() calls in brain package -- regression risk)
echo.
echo --- E2. Pre-commit grep guard for .resolve() ---
powershell -NoProfile -Command "Test-Path '.pre-commit-config.yaml' | ForEach-Object { if($_) { Select-String '.pre-commit-config.yaml' -Pattern 'resolve' -SimpleMatch -Quiet } else { 'no pre-commit config' } }"
echo.
echo --- E3. archive/legacy_python/ size (DR backup but bloat) ---
powershell -NoProfile -Command "$d='archive/legacy_python'; if (Test-Path $d) { Write-Host ('  size: {0:N1} MB  files: {1}' -f ((Get-ChildItem $d -Recurse | Measure-Object Length -Sum).Sum/1MB), (Get-ChildItem $d -Recurse -File).Count) }"
