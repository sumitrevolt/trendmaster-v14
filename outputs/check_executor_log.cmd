@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === python_executor.log last 40 lines ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 40 -ErrorAction SilentlyContinue"
echo.
echo === Search for skip/reject/blocked/safeguard reasons ===
powershell -NoProfile -Command "Select-String -Path 'logs\python_executor.log' -Pattern 'skip|reject|block|safeguard|veto|error' | Select-Object -Last 20 | ForEach-Object { '  ' + $_.Line }"
echo.
echo === Count python_signal_executor instances ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Measure-Object | Select-Object @{N='ExecutorCount';E={$_.Count}}"
