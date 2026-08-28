@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Run script and capture output ===
.venv\Scripts\python.exe tools\daily_maintenance.py
echo.
echo === Backups dir state ===
powershell -NoProfile -Command "if (Test-Path 'backups') { Get-ChildItem 'backups' -Recurse | Select-Object FullName, @{N='SizeKB';E={[math]::Round($_.Length/1024,1)}} | Format-Table -AutoSize } else { 'backups/ does not exist' }"
