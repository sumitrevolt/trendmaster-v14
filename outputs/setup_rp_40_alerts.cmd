@echo off
REM Launches capture_and_create_40_alerts.py (Playwright headed browser).
REM Phase 1 (3 min): operator creates 2 template alerts in the opened browser
REM   - BUY: Rocket Prime Engine -> Buy Observation #1 -> Crossing Up -> 0
REM   - SELL: Rocket Prime Engine -> Sell Observation #1 -> Crossing Up -> 0
REM Phase 2 (auto): script creates 38 more alerts via TV INTERNAL API.
REM
REM This is the proven path. TV's create_alert payload is undocumented;
REM operator's manual capture in Phase 1 is irreducible (verified via web search).

cd /d "%~dp0\.."
echo.
echo === Launching capture_and_create_40_alerts.py ===
echo === A Chromium window will open at tradingview.com/chart/ ===
echo.
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\..\tools\tv_alert_setup\capture_and_create_40_alerts.py"
echo.
echo === Done — check above for created/failed counts ===
pause
