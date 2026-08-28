@echo off
REM Delete + recreate 20 RP alerts with plot URL placeholders. Bypasses
REM Pine alert() body override by putting {{plot_0}}..{{plot_9}} in URL.
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\..\tools\tv_alert_setup\recreate_rp_with_plot_url.py" > "%~dp0\..\logs\recreate_rp_with_plot_url.log" 2>&1
type "%~dp0\..\logs\recreate_rp_with_plot_url.log"
echo.
timeout /t 30 /nobreak > nul
