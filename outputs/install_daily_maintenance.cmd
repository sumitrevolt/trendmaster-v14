@echo off
echo === Install daily maintenance task (23:50 daily) ===
schtasks /Create ^
    /TN "TrendMaster Daily Maintenance" ^
    /TR "wscript.exe \"C:\Users\Ratanshila\Documents\autmated trading\tools\daily_maintenance.vbs\"" ^
    /SC DAILY /ST 23:50 ^
    /F
echo.
schtasks /Query /TN "TrendMaster Daily Maintenance" /FO LIST
echo.
echo === Trigger one-shot now (rotate + backup happens immediately) ===
schtasks /Run /TN "TrendMaster Daily Maintenance"
ping 127.0.0.1 -n 8 >nul
echo.
echo === Tail log ===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\daily_maintenance.log' -Tail 30 -ErrorAction SilentlyContinue"
echo.
echo === Verify backups created ===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\Documents\autmated trading\backups' -Recurse -ErrorAction SilentlyContinue | Select-Object FullName, Length | Format-Table -AutoSize"
