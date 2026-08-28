@echo off
REM Install all TrendMaster maintenance schtasks (idempotent).
REM Run as user (no admin needed for /SC).

set ROOT=C:\Users\Ratanshila\Documents\autmated trading
set PYTHONW=%ROOT%\.venv\Scripts\pythonw.exe

echo === Process watchdog (every 2 minutes) ===
schtasks /Create /F /TN "TrendMaster Process Watchdog" ^
  /TR "\"%PYTHONW%\" -u \"%ROOT%\tools\process_watchdog.py\"" ^
  /SC MINUTE /MO 2 /RL LIMITED

echo === Logon launcher (executor + trailing manager + receiver) ===
REM ONLOGON works for current user without admin (ONSTART needs admin)
schtasks /Create /F /TN "TrendMaster Logon Launcher" ^
  /TR "\"%PYTHONW%\" -u \"%ROOT%\tools\process_watchdog.py\"" ^
  /SC ONLOGON /RL LIMITED /DELAY 0001:00

echo === Hourly snapshot (every hour at :05) ===
schtasks /Create /F /TN "TrendMaster Hourly Snapshot" ^
  /TR "\"%PYTHONW%\" -u \"%ROOT%\tools\hourly_telegram_snapshot.py\"" ^
  /SC HOURLY /ST 00:05 /RL LIMITED

echo === Daily summary (23:00 IST) ===
schtasks /Create /F /TN "TrendMaster Daily Summary" ^
  /TR "\"%PYTHONW%\" -u \"%ROOT%\tools\daily_telegram_summary.py\"" ^
  /SC DAILY /ST 23:00 /RL LIMITED

echo.
echo === Verification ===
schtasks /Query /TN "TrendMaster Process Watchdog" /FO LIST
schtasks /Query /TN "TrendMaster Boot Launcher" /FO LIST
schtasks /Query /TN "TrendMaster Hourly Snapshot" /FO LIST
schtasks /Query /TN "TrendMaster Daily Summary" /FO LIST

echo.
echo === Done ===
