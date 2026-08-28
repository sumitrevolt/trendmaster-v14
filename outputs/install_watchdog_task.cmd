@echo off
setlocal
set TASK=TrendMaster Health Watchdog
set PY=C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\python.exe
set SCRIPT=C:\Users\Ratanshila\Documents\autmated trading\tools\health_watchdog.py

echo === removing old task if any ===
schtasks /Delete /TN "%TASK%" /F >nul 2>&1

echo === creating fresh task (1-min interval) ===
schtasks /Create /TN "%TASK%" /TR "\"%PY%\" \"%SCRIPT%\" --once" /SC MINUTE /MO 1 /RL LIMITED /F
if errorlevel 1 (
    echo [X] schtasks /Create failed.
    exit /b 1
)

echo.
echo === verify task is registered ===
schtasks /Query /FO CSV /NH | findstr /I "Health Watchdog"

echo.
echo === run task once now to seed ===
schtasks /Run /TN "%TASK%"
timeout /T 3 /NOBREAK >nul

echo.
echo === watchdog state after first run ===
type "C:\Users\Ratanshila\Documents\autmated trading\logs\watchdog_state.json"
