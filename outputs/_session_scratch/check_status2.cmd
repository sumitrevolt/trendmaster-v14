@echo off
echo === All cmd.exe windows ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Select-Object ProcessId, ParentProcessId, @{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(120, $_.CommandLine.Length))}} | Format-Table -AutoSize"
echo.
echo === Python procs ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Select-Object ProcessId, ParentProcessId, @{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(140, $_.CommandLine.Length))}} | Format-Table -AutoSize"
echo.
echo === Chromium procs ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup|_browser_profile' } | Select-Object ProcessId | Measure-Object"
