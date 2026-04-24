@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo ==========================================================
echo   FINAL SYSTEM VERIFICATION
echo ==========================================================

echo.
echo [1/6] Unit tests
python -m pytest tests/ -q --no-header --tb=no 2>&1 | findstr "passed failed"

echo.
echo [2/6] Module imports + settings flags
python main.py smoke 2>&1 | findstr /V "INFO WARNING"

echo.
echo [3/6] Dashboard probe
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing 'http://localhost:8000/healthz' -TimeoutSec 3).Content } catch { 'dashboard not responding' }"

echo.
echo [4/6] Brain alive check
powershell -NoProfile -Command "if (Test-Path 'logs\brain.pid') { $p = (Get-Content logs\brain.pid).Trim(); $alive = Get-Process -Id $p -ErrorAction SilentlyContinue; if ($alive) { Write-Host ('Brain PID ' + $p + ' ALIVE (' + [math]::Round($alive.WorkingSet64/1MB,1) + ' MB)') } else { Write-Host 'Brain pidfile stale' } }"

echo.
echo [5/6] Per-symbol config loaded
python -c "from ai_trading_agents.pair_params import PAIR_PARAMS; print(f'Symbols loaded: {len(PAIR_PARAMS)}'); print('Top 5 profit:'); import json; rows = sorted(PAIR_PARAMS.items(), key=lambda x: -x[1].get('gross_r', 0))[:5]; [print(f'  {s:8s}  SL={p[\"sl_atr_mult\"]}  TP={p[\"tp_atr_mult\"]}  ADX={p[\"adx_min\"]}  gross=${p[\"gross_r\"]:.1f}') for s,p in rows]"

echo.
echo [6/6] Signal files fresh?
powershell -NoProfile -Command "$base='C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal'; $found = Get-ChildItem $base -Filter 'trendmaster_signals_*.json' -Recurse -ErrorAction SilentlyContinue; if ($found) { $fresh = ($found | Where-Object { ((Get-Date) - $_.LastWriteTime).TotalSeconds -lt 30 } | Measure-Object).Count; $total = ($found | Measure-Object).Count; Write-Host ('Signal files: ' + $fresh + '/' + $total + ' fresh within 30s') } else { Write-Host 'No signal files found' }"

echo.
echo ==========================================================
echo   VERIFICATION DONE
echo ==========================================================
