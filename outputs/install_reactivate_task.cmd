@echo off
REM ===========================================================================
REM Install the hourly TV alert reactivation task.
REM Runs as user (no admin needed). Hidden via .vbs wrapper.
REM ===========================================================================
echo === Installing scheduled task: TrendMaster Reactivate Alerts ===
schtasks /Create ^
    /TN "TrendMaster Reactivate Alerts" ^
    /TR "wscript.exe \"C:\Users\Ratanshila\Documents\autmated trading\tools\reactivate_alerts_hourly.vbs\"" ^
    /SC HOURLY /MO 1 ^
    /ST 09:00 ^
    /F
echo.
echo === Verifying ===
schtasks /Query /TN "TrendMaster Reactivate Alerts" /FO LIST
echo.
echo === Triggering one-shot run NOW so first heal happens immediately ===
schtasks /Run /TN "TrendMaster Reactivate Alerts"
echo.
echo === Tail of reactivate log (after a few sec) ===
ping 127.0.0.1 -n 8 >nul
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\reactivate_inactive.log' -Tail 20 -ErrorAction SilentlyContinue"
