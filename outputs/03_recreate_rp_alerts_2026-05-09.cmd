@echo off
REM =====================================================================
REM 03_recreate_rp_alerts_2026-05-09.cmd
REM
REM Recreate the 20 dead Rocket Prime alerts (5 pairs x 4 timeframes).
REM
REM What this does:
REM   - Opens a HEADED Chromium browser pointed at TradingView
REM   - You log in (if cookies are stale)
REM   - Script auto-detects login, then:
REM       1. Lists existing Rocket Prime alerts (probably 0 - all expired)
REM       2. Deletes them if any
REM       3. Creates 20 new alerts pointing at:
REM            https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?...
REM       4. Each alert has body containing {{plot_0}}..{{plot_9}} placeholders
REM          (TV will substitute the indicator's own text at runtime, but
REM          the URL has &symbol={{ticker}}&tf={{interval}} which always
REM          delivers symbol+timeframe. INFERRED mode handles direction.)
REM
REM Time estimate: 1-2 minutes if you're already logged in to TV; 5 if not.
REM =====================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============================================================
echo   Recreating 20 Rocket Prime alerts
echo   Top 5 pairs: XAUUSD EURUSD USDJPY GBPUSD BTCUSD
echo   Timeframes:  M5 M15 M30 H1
echo ============================================================
echo.
echo If a Chromium window opens to TradingView and asks you to log in,
echo do so normally. The script will detect login and continue.
echo.
echo Press Ctrl+C now to abort, or any key to start.
pause >nul

.venv\Scripts\python.exe tools\tv_alert_setup\recreate_with_login.py

echo.
echo ============================================================
echo   DONE -- check the output above for any [FAIL] lines
echo ============================================================
echo.
echo Verify pipeline is ready:
echo   outputs\01_verify_pipeline_2026-05-09.cmd
echo.
echo Then watch for the first real Rocket Prime fire:
echo   powershell -Command "Get-Content 'logs\tv_webhook.log' -Tail 5 -Wait"
echo.
