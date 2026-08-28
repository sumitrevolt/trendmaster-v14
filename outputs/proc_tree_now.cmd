@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === ALL python.exe processes (full picture) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Select-Object ProcessId, ParentProcessId, @{N='Started';E={$_.CreationDate}}, @{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(100, $_.CommandLine.Length))}} | Format-Table -AutoSize"
echo.
echo === pythonw.exe ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Select-Object ProcessId, ParentProcessId, @{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(100, $_.CommandLine.Length))}} | Format-Table -AutoSize"
echo.
echo === brain.pid file value ===
type logs\brain.pid 2>nul
