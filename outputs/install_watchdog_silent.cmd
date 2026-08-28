@echo off
setlocal
set TASK=TrendMaster Health Watchdog
set PYW=C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\pythonw.exe
set SCRIPT=C:\Users\Ratanshila\Documents\autmated trading\tools\health_watchdog.py

echo === removing OLD popup-causing task (python.exe) ===
schtasks /Delete /TN "%TASK%" /F >nul 2>&1

echo === creating SILENT task (pythonw.exe — no console window) ===
schtasks /Create /TN "%TASK%" /TR "\"%PYW%\" \"%SCRIPT%\" --once" /SC MINUTE /MO 1 /RL LIMITED /F
if errorlevel 1 (
    echo [X] schtasks /Create failed.
    exit /b 1
)

echo.
echo === verify task uses pythonw.exe (silent) ===
schtasks /Query /TN "%TASK%" /FO LIST /V > "%TEMP%\verify_wd.txt" 2>nul
findstr /N "Task To Run" "%TEMP%\verify_wd.txt"

echo.
echo === DONE — no more terminal popup every minute ===
