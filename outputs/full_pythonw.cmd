@echo off
echo === Full command line of every pythonw.exe ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Select-Object ProcessId, @{N='Cmd';E={$_.CommandLine}} | Format-List"
