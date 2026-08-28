@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === backup\ contents ===
powershell -NoProfile -Command "if (Test-Path 'backup') { Get-ChildItem 'backup' -Recurse | Select-Object Name, @{N='SizeKB';E={[math]::Round($_.Length/1024,1)}}, LastWriteTime | Format-Table } else { Write-Host '  backup/ does not exist' }"
echo.
echo === Existing scheduled tasks (TrendMaster) ===
schtasks /Query /FO TABLE | findstr /i "TrendMaster"
echo.
echo === Run pre-existing daily_maintenance.py ===
.venv\Scripts\python.exe -u tools\daily_maintenance.py 2>&1
echo Exit: %ERRORLEVEL%
echo.
echo === Tail daily_maintenance.log ===
powershell -NoProfile -Command "Get-Content 'logs\daily_maintenance.log' -Tail 6"
