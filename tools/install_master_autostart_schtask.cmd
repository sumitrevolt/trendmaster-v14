@echo off
set "TN=TrendMaster Master Autostart"
set "PYW=C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\pythonw.exe"
set "SCRIPT=C:\Users\Ratanshila\Documents\autmated trading\tools\master_autostart.py"
schtasks /Delete /TN "%TN%" /F >nul 2>&1
schtasks /Create /TN "%TN%" /TR "\"%PYW%\" \"%SCRIPT%\"" /SC ONLOGON /F
schtasks /Query /TN "%TN%" /FO LIST
