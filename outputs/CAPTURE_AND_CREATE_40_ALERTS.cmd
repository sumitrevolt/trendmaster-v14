@echo off
REM ============================================================================
REM   CAPTURE_AND_CREATE_40_ALERTS.cmd
REM
REM   The FINAL Rocket Prime fix. Run this ONCE, do 2 manual alerts in TV
REM   while it watches, then it auto-creates the other 38.
REM
REM   Total your time: ~5 minutes (creating 2 alerts manually).
REM   Total wall-clock: ~6-7 minutes.
REM
REM   What you'll do (instructions also printed by the script):
REM     1. A Chrome window opens at TradingView.
REM     2. You create ONE BUY alert: Condition = Rocket Prime Engine →
REM        "Buy Observation #1" → Crossing Up → 0. Webhook URL ends with
REM        &direction=buy. Save.
REM     3. You create ONE SELL alert: similar but Sell plot, &direction=sell. Save.
REM     4. Script auto-deletes old 20 alerts + creates 38 more (5 pairs ×
REM        4 TFs × 2 dirs - your 2 manual = 38).
REM     5. You verify by watching logs/tv_webhook.log for next signal.
REM ============================================================================
setlocal
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo.
echo === Final Rocket Prime fix: capture + create 40 alerts ===
echo.
.venv\Scripts\python.exe tools\tv_alert_setup\capture_and_create_40_alerts.py
echo.
echo === Captured templates ===
if exist "tools\tv_alert_setup\captured_buy_alert.json" (
    echo  [OK] tools\tv_alert_setup\captured_buy_alert.json
)
if exist "tools\tv_alert_setup\captured_sell_alert.json" (
    echo  [OK] tools\tv_alert_setup\captured_sell_alert.json
)
echo.
echo Watch live for next Rocket Prime signal:
echo    powershell -Command "Get-Content 'logs\tv_webhook.log' -Tail 5 -Wait"
echo Expect 'URL-DIRECTION BUY' or 'URL-DIRECTION SELL' lines.
echo.
pause
endlocal
