@echo off
REM Re-create the 2 most-frequent schtasks pointing at VBS wrappers (zero flash).

set ROOT=C:\Users\Ratanshila\Documents\autmated trading

echo === Process Watchdog (every 2 min) ===
schtasks /Delete /TN "TrendMaster Process Watchdog" /F 2>nul
schtasks /Create /F /TN "TrendMaster Process Watchdog" ^
  /TR "wscript.exe \"%ROOT%\tools\hidden_process_watchdog.vbs\"" ^
  /SC MINUTE /MO 2 /RL LIMITED

echo === TV Webhook Watchdog (every 5 min) ===
schtasks /Delete /TN "TrendMaster TV Webhook Watchdog" /F 2>nul
schtasks /Create /F /TN "TrendMaster TV Webhook Watchdog" ^
  /TR "wscript.exe \"%ROOT%\tools\hidden_tv_webhook_watchdog.vbs\"" ^
  /SC MINUTE /MO 5 /RL LIMITED

echo.
echo === Done ===
