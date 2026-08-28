@echo off
REM Recreate Rocket Prime alerts for 24 volatile pairs × M5+M15 = 48 alerts.
REM Pair list lives in reports/volatile_pairs.json — edit there to add/remove.
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\..\tools\tv_alert_setup\recreate_rp_volatile_m5m15.py" > "%~dp0\..\logs\recreate_rp_volatile_m5m15.log" 2>&1
type "%~dp0\..\logs\recreate_rp_volatile_m5m15.log"
echo.
timeout /t 30 /nobreak > nul
