@echo off
set ROOT=C:\Users\Ratanshila\Documents\autmated trading
set PYTHONW=%ROOT%\.venv\Scripts\pythonw.exe

REM Run weekly on Sunday at 02:00 IST — quiet hours, weekly cadence
schtasks /Create /F /TN "TrendMaster TV Alert Renewer" ^
  /TR "\"%PYTHONW%\" -u \"%ROOT%\tools\tv_alert_setup\renew_expiring_alerts.py\"" ^
  /SC WEEKLY /D SUN /ST 02:00 /RL LIMITED

echo.
schtasks /Query /TN "TrendMaster TV Alert Renewer" /FO LIST
