@echo off
REM ============================================================================
REM   rocket_prime_only_mode_2026-05-09.cmd
REM
REM   Switches the bot to Rocket-Prime-only mode per operator decision
REM   2026-05-09 00:50 IST.
REM
REM   What this does:
REM     1. Disable TrendMaster Local Signal Generator schtask (no more
REM        EMA-cross signals firing every 5 min)
REM     2. Kill the local_signal_generator if currently running
REM     3. Restart executor (the patched ALLOWED_STRATEGIES no longer accepts
REM        "local_generator" tag, so any in-flight files won't trade)
REM     4. Print the manual TV setup steps the operator has to run ONCE
REM        to make Rocket Prime alerts deliver direction info
REM
REM   What this does NOT do:
REM     - Does NOT delete the local_signal_generator code (rollback path)
REM     - Does NOT touch existing TV alerts (they still fire but get rejected
REM       at the receiver because Pine alert() override leaves dir=NONE)
REM
REM   Rollback to local_generator mode:
REM     - Uncomment "local_generator" in tools/python_signal_executor.py:362
REM     - Re-enable schtask: schtasks /Change /TN "TrendMaster Local Signal Generator" /ENABLE
REM     - Restart executor
REM ============================================================================
setlocal
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo.
echo ############################################################
echo #
echo #   ROCKET-PRIME-ONLY MODE  (2026-05-09)
echo #
echo ############################################################
echo.

echo === STEP 1: Disabling TrendMaster Local Signal Generator schtask ===
schtasks /Change /TN "TrendMaster Local Signal Generator" /DISABLE 2>nul
if errorlevel 1 (
    echo  [info] schtask not found OR already disabled
) else (
    echo  [OK] schtask disabled
)

echo.
echo === STEP 2: Killing live local_signal_generator processes ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*local_signal_generator*' } | ForEach-Object { Write-Host ('   PID ' + $_.ProcessId); taskkill /F /PID $_.ProcessId 2>$null }"

echo.
echo === STEP 3: Cleaning stale local_generator signal files ===
mkdir "backup\rocket_prime_only_2026-05-09" 2>nul
move /Y "C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals*.json" "backup\rocket_prime_only_2026-05-09\" 2>nul
echo  [OK] stale signals archived

echo.
echo === STEP 4: Restarting executor with patched ALLOWED_STRATEGIES ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host ('   PID ' + $_.ProcessId); taskkill /F /PID $_.ProcessId 2>$null }"
del /f /q logs\python_signal_executor.lock 2>nul
ping 127.0.0.1 -n 5 >nul
start "TM Executor - ROCKET PRIME ONLY" /MIN cmd /c "title TM Executor && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u tools\python_signal_executor.py 1>> logs\python_signal_executor.out 2>> logs\python_signal_executor.err"
ping 127.0.0.1 -n 8 >nul

echo.
echo === STEP 5: Verify executor banner shows local_generator NOT in whitelist ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 15 | Select-String -Pattern 'STARTUP BANNER|ALLOWED_STRATEGIES|safeguards'"

echo.
echo ############################################################
echo #
echo #   STATUS  -  Bot is now in ROCKET-PRIME-ONLY mode
echo #
echo #   - local_signal_generator: DISABLED
echo #   - executor whitelist: only Rocket Prime variants
echo #   - until TV chain is fixed, NO trades will fire
echo #
echo #   Why no trades right now:
echo #     Rocket Prime is an invite-only Pine indicator. It uses Pine
echo #     `alert()` function calls internally. TradingView ignores the
echo #     alert dialog "Message" field for `alert()`-driven alerts and
echo #     sends the indicator's hardcoded `#### {{ticker}} ####` text
echo #     instead. Direction info never reaches the webhook.
echo #
echo ############################################################
echo.
echo To activate Rocket Prime trades, see:
echo   docs\guides\ROCKET_PRIME_40_ALERT_SETUP.md
echo.
echo Quick summary of next steps (5-10 min in TV UI):
echo   1. Open TradingView, add Rocket Prime to one chart (any pair)
echo   2. Click bell icon -^> Add Alert
echo   3. Condition: choose "Rocket Prime Engine"
echo      Look at the dropdown -^> if you see options like
echo      "plot_0 crossing up" or named like "Buy Signal", select that
echo      ONLY for buy events. Webhook URL: existing + "?direction=buy"
echo   4. Repeat for SELL with "plot_1 crossing up" -^> "?direction=sell"
echo   5. Run outputs\capture_rocket_prime_templates_2026-05-09.cmd
echo      (script will Playwright-watch your manual alert creation, capture
echo       the POST payload, save as buy/sell templates)
echo   6. Then run outputs\create_40_alerts_2026-05-09.cmd to bulk-create
echo      the remaining 38 alerts ^(5 pairs * 4 TFs * 2 dirs = 40 total^)
echo.
pause
endlocal
