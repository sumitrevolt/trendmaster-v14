@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Tail daily_maintenance.log (last 20 lines) ===
powershell -NoProfile -Command "Get-Content 'logs\daily_maintenance.log' -Tail 20 -ErrorAction SilentlyContinue"
echo.
echo === Backups dir ===
powershell -NoProfile -Command "if (Test-Path 'backups') { Get-ChildItem 'backups' -Recurse | Select-Object FullName, @{N='SizeKB';E={[math]::Round($_.Length/1024,1)}} | Format-Table } else { 'backups/ does not exist' }"
echo.
echo === Run my script directly to verify ===
.venv\Scripts\python.exe tools\daily_maintenance.py
