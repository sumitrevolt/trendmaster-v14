@echo off
REM ===========================================================================
REM 5-PAIR ROCKET PRIME ALERT SETUP -- API METHOD
REM Usage: double-click. Deletes all existing Rocket Prime alerts, recreates
REM 5 pairs (XAUUSD, EURUSD, USDJPY, GBPUSD, BTCUSD) x 4 TFs (M5/M15/M30/H1).
REM Pulls top-5 list from reports/top_5_pairs.json. Edit there to change pairs.
REM ===========================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Pre-flight: webhook health ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=8); print('  health:', r.status)"
echo.
echo === Running delete_all_rocket_then_recreate.py via TV API ===
.venv\Scripts\python.exe tools\tv_alert_setup\delete_all_rocket_then_recreate.py
echo.
echo === Done. Press any key to close ===
pause
