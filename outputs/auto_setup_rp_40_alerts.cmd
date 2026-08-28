@echo off
REM Fully autonomous TV alert setup — Playwright drives the alert dialog.
REM No operator clicks needed (falls back to manual if UI selector breaks).
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\..\tools\tv_alert_setup\auto_capture_rp_alerts.py" > "%~dp0\..\logs\auto_capture_rp_alerts.log" 2>&1
type "%~dp0\..\logs\auto_capture_rp_alerts.log"
echo.
timeout /t 60 /nobreak > nul
