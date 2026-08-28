@echo off
echo === Installing brain liveness watchpet (every 5 min) ===
schtasks /Create ^
    /TN "TrendMaster Brain Watchpet" ^
    /TR "wscript.exe \"C:\Users\Ratanshila\Documents\autmated trading\tools\watchpet_brain_alive.vbs\"" ^
    /SC MINUTE /MO 5 ^
    /F
echo.
echo === Verify ===
schtasks /Query /TN "TrendMaster Brain Watchpet" /FO LIST
echo.
echo === Test-run NOW ===
schtasks /Run /TN "TrendMaster Brain Watchpet"
ping 127.0.0.1 -n 5 >nul
echo.
echo === Tail watchpet log ===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\watchpet_brain.log' -Tail 10 -ErrorAction SilentlyContinue"
