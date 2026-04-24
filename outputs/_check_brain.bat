@echo off
timeout /t 18 /nobreak >nul
echo ===PROCESSES===
wmic process where "name='python.exe'" get processid,commandline 2>nul
echo ===LOG TAIL===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\trend_master_brain.out' -Tail 20"
echo ===ERR TAIL===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\trend_master_brain.err' -Tail 10 -ErrorAction SilentlyContinue"
