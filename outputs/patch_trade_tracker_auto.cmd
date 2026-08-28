@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\patch_trade_tracker_min_deal_ts.py" > "%~dp0\..\logs\patch_trade_tracker.log" 2>&1
type "%~dp0\..\logs\patch_trade_tracker.log"
echo.
timeout /t 30 /nobreak > nul
