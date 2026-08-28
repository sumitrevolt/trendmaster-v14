@echo off
set ROOT=C:\Users\Ratanshila\Documents\autmated trading
set PYTHONW=%ROOT%\.venv\Scripts\pythonw.exe

schtasks /Create /F /TN "TrendMaster Daily Maintenance" ^
  /TR "\"%PYTHONW%\" -u \"%ROOT%\tools\daily_maintenance.py\"" ^
  /SC DAILY /ST 00:30 /RL LIMITED

echo.
schtasks /Query /TN "TrendMaster Daily Maintenance" /FO LIST
