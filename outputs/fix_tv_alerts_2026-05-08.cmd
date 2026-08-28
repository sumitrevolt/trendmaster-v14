@echo off
REM ============================================================================
REM   fix_tv_alerts_2026-05-08.cmd  —  Recreate all 20 Rocket Prime alerts with
REM   the correct plot-placeholder template
REM
REM   ROOT CAUSE (logs/tv_webhook.log evidence):
REM     Your existing TV alerts send body  '#### EURUSD ####'  with no direction.
REM     Webhook receiver logs:
REM       REJECT no-direction signal for EURUSD ... (INFERRED disabled per safety
REM       policy 2026-05-08; OR fix TV alert template to include plot/direction)
REM     Result: 5m alerts deliver but dir=NONE (no trade); 15m alerts get HTTP 422
REM     when they coincide with a news-blackout window.
REM
REM   FIX: recreate all 20 alerts using the template that recreate_with_login.py
REM   already has — it embeds {{plot_0}}..{{plot_9}} so receiver can extract:
REM       p0 > 0  AND  p1 == 0  →  BUY
REM       p1 > 0  AND  p0 == 0  →  SELL
REM   This is the ONLY way to get direction out of an invite-only indicator
REM   like Rocket Prime whose alert text doesn't include "buy"/"sell".
REM
REM   WHAT HAPPENS WHEN YOU RUN THIS:
REM     1. A real Chrome browser window opens at TradingView chart page.
REM     2. If your TV cookies are still valid → script auto-detects and proceeds.
REM     3. If cookies expired → sign in via Google/email; script polls every 3s
REM        and proceeds the moment login succeeds (8 min timeout).
REM     4. Script DELETES all 20 existing Rocket Prime alerts.
REM     5. Script CREATES 20 fresh alerts (5 pairs × 4 TFs) with proper template.
REM     6. You'll see "[OK] {sym} {tf} aid=..." for each successful create.
REM ============================================================================
setlocal
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo.
echo ============================================================
echo   Pre-flight  -  webhook reachability check
echo ============================================================
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.Request('https://shadow-cosmos-unending.ngrok-free.dev/health', headers={'ngrok-skip-browser-warning':'true'}); resp=u.urlopen(r, timeout=10); print('  PUBLIC OK status=', resp.status, 'body=', resp.read().decode())" 2>nul
if errorlevel 1 (
    echo [X] Webhook not reachable. Run outputs\fix_ngrok.cmd first.
    pause
    exit /b 2
)

echo.
echo ============================================================
echo   Recreating all 20 Rocket Prime alerts with plot template
echo ============================================================
echo  Pairs:        XAUUSD, EURUSD, USDJPY, GBPUSD, BTCUSD
echo  Timeframes:   M5, M15, M30, H1
echo  Template:     RP^|{{ticker}}^|tf={{interval}}^|p0={{plot_0}}^|p1={{plot_1}}^|...^|p9={{plot_9}}^|c={{close}}^|t={{timenow}}
echo  Webhook:      https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=...&symbol=^<sym^>&tf=^<tf^>
echo.
echo  ^>^> A Chrome window will pop up.  If TV asks for login, sign in (Google
echo     or email).  Script auto-detects login via API and proceeds.
echo.
.venv\Scripts\python.exe tools\tv_alert_setup\recreate_with_login.py
set RC=%ERRORLEVEL%

echo.
echo ============================================================
echo   Verifying alert messages contain plot placeholders
echo ============================================================
.venv\Scripts\python.exe tools\tv_alert_setup\verify_alert_messages.py 2>nul
echo.

if %RC% neq 0 (
    echo [X] recreate_with_login.py exited with code %RC%
    echo     Common causes:
    echo       2 = TV login timeout — re-run within 8 min and stay on the chart
    echo     Check logs/tv_alert_setup/ for the latest run log.
) else (
    echo ============================================================
    echo   DONE — alerts recreated.
    echo ============================================================
    echo.
    echo  NEXT STEP: wait for the next M5 close (within 5 min). The next signal
    echo  will arrive with body 'RP^|EURUSD^|tf=5^|p0=1.0^|p1=0.0^|...' and the
    echo  receiver will extract direction. Verify with:
    echo.
    echo    type logs\tv_webhook.log ^| findstr /C:"PLOT-DIRECTION" /C:"TV-^>EA OK"
    echo    type logs\tv_plot_values.jsonl ^| more
    echo    type logs\python_executor.log ^| findstr /C:"placed order" /C:"SAFEGUARD"
)
echo.
pause
endlocal
