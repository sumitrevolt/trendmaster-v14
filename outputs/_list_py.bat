@echo off
tasklist /FI "IMAGENAME eq python.exe" /NH /FO CSV
echo ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'name=\"python.exe\"' | Select-Object ProcessId, @{n='Cmd';e={$_.CommandLine}} | Format-Table -AutoSize -Wrap"
