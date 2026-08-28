@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === All brain processes RIGHT NOW (with PID + start time) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object ProcessId, ParentProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
echo.
echo === Multi-market dispatcher procs (different module) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*multi_market_dispatcher*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
echo.
echo === Lock file ===
powershell -NoProfile -Command "if (Test-Path 'logs\brain.lock') { 'logs\brain.lock contents: ' + (Get-Content 'logs\brain.lock') } else { 'no lock' }"
echo.
echo === Brain PID file ===
powershell -NoProfile -Command "if (Test-Path 'logs\brain.pid') { 'logs\brain.pid: ' + (Get-Content 'logs\brain.pid') } else { 'no pid file' }"
