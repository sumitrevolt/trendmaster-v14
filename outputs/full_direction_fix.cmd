@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === STEP 1: Restart webhook with plot-direction parser ===
call start_tv_webhook.cmd
echo.
echo === STEP 2: Verify all 3 priority blocks present ===
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_webhook_receiver.py' -Pattern 'rocket_prime_plot0|rocket_prime_url_direction|rocket_prime_inferred' | Select-Object -Last 6 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === STEP 3: Recreate 20 alerts with new message field (plots in body) ===
.venv\Scripts\python.exe tools\tv_alert_setup\delete_all_rocket_then_recreate.py
echo.
echo === STEP 4: Verify alerts have new message ===
.venv\Scripts\python.exe outputs\verify_alerts_simple.py
