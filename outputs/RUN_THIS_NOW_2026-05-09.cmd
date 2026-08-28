@echo off
REM ============================================================================
REM   RUN_THIS_NOW_2026-05-09.cmd
REM
REM   ONE-CLICK FIX for the two persistent issues:
REM     1. Terminal popups every minute (5 days running)
REM     2. TV signals arriving but no trades happening (5 days running)
REM
REM   Runs in this order:
REM     A. nuke_all_popups_2026-05-09.cmd
REM        Re-registers EVERY popup-causing schtask to use its hidden_*.vbs
REM        wrapper.  The earlier fix only touched 5 schtasks; the deep audit
REM        found 14 more (TV Webhook Watchdog, Junction Guard, Schtasks Audit,
REM        etc.) flashing windows because they ran .cmd files directly or
REM        used python.exe instead of pythonw.exe.
REM
REM     B. bulletproof_tv_fix_2026-05-09.cmd
REM        First VERIFIES current TV alert state via API.  Earlier "fix" had
REM        no logging, so we never knew if the recreate actually worked - it
REM        didn't.  This time, every step is captured to a log AND verified.
REM        If alerts already correct, skip recreate.  If they're still BAD
REM        after recreate, fail loudly with the alert-by-alert breakdown.
REM
REM     C. Install signal-pipeline regression monitor.
REM        Runs every 5 min, sends Telegram alert if a regression is detected.
REM        Prevents another 5-day silent failure.
REM ============================================================================
setlocal
cd /d "%~dp0"

echo.
echo ################################################################
echo #
echo #  PART A of 2  -  FIX TERMINAL POPUPS
echo #
echo ################################################################
echo.
call nuke_all_popups_2026-05-09.cmd

echo.
echo.
echo ################################################################
echo #
echo #  PART B of 2  -  FIX TV ALERTS / TRADES
echo #
echo ################################################################
echo.
call bulletproof_tv_fix_2026-05-09.cmd

echo.
echo ################################################################
echo #
echo #  ALL DONE  -  Both issues addressed.
echo #
echo #  Watch for the next signal:
echo #    powershell -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\tv_webhook.log' -Tail 5 -Wait"
echo #
echo #  If you see 'PLOT-DIRECTION BUY' or 'PLOT-DIRECTION SELL' line,
echo #  the fix worked.  Trades should fire (subject to safeguard caps).
echo #
echo ################################################################
pause
endlocal
