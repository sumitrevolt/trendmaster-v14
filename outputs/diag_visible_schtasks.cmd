@echo off
cd /d "%~dp0\.."
echo === All TrendMaster schtasks - identify which spawn visible cmd ===
echo.
schtasks /Query /TN "\TrendMaster Health Watchdog" /V /FO LIST > outputs\schtask_diag.txt 2>nul
schtasks /Query /TN "\TrendMaster Process Watchdog" /V /FO LIST >> outputs\schtask_diag.txt 2>nul
echo ============================================== >> outputs\schtask_diag.txt
echo ALL TRENDMASTER TASKS >> outputs\schtask_diag.txt
echo ============================================== >> outputs\schtask_diag.txt
schtasks /Query /FO LIST /V | findstr /R /C:"TaskName" /C:"Task To Run" /C:"Status" /C:"Schedule Type" > outputs\schtask_all_runs.txt
echo Done. Results in outputs\schtask_diag.txt and outputs\schtask_all_runs.txt
timeout /t 5 /nobreak > nul
