@echo off
REM Modify existing 20 Rocket Prime alerts via TV API: add &p0={{plot_0}}..&p9={{plot_9}}
REM placeholders to webhook URL. Bypasses Pine alert() override of message body.
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\..\tools\tv_alert_setup\update_rp_alerts_with_plot_url.py" > "%~dp0\..\logs\update_rp_alerts_url.log" 2>&1
type "%~dp0\..\logs\update_rp_alerts_url.log"
echo.
echo === Now restart webhook receiver to pick up code changes ===
timeout /t 30 /nobreak > nul
