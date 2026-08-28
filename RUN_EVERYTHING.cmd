@echo off
rem ============================================================
rem  Master setup script - generated 2026-04-29
rem  Runs trading bot setup AND restarts OpenClaw gateway
rem ============================================================

setlocal EnableDelayedExpansion
set LOG=C:\Users\Ratanshila\Documents\autmated trading\outputs\run_everything.log
set TS=%DATE% %TIME%
echo. > "%LOG%"
echo [%TS%] starting RUN_EVERYTHING.cmd >> "%LOG%"

cd /d "C:\Users\Ratanshila\Documents\autmated trading"
if errorlevel 1 (
    echo [ERROR] cannot cd to trading folder >> "%LOG%"
    type "%LOG%"
    pause
    exit /b 1
)

echo. >> "%LOG%"
echo === [1/5] which python in venv === >> "%LOG%"
".venv\Scripts\python.exe" --version >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === [2/5] pip install pyyaml === >> "%LOG%"
".venv\Scripts\pip.exe" install pyyaml >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === [3/5] sync_config_to_mqh.py === >> "%LOG%"
".venv\Scripts\python.exe" tools\sync_config_to_mqh.py >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === [4/5] enable_phase_b3_ml.py --verify === >> "%LOG%"
".venv\Scripts\python.exe" tools\enable_phase_b3_ml.py --verify >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo === [5/5] launching OpenClaw restart in new window === >> "%LOG%"
start "OpenClaw Gateway" cmd /k "C:\Users\Ratanshila\.openclaw\restart_gateway.cmd"

echo. >> "%LOG%"
echo [%DATE% %TIME%] DONE - results above >> "%LOG%"

cls
echo ============================================================
echo  RUN_EVERYTHING.cmd - complete
echo ============================================================
type "%LOG%"
echo.
echo ============================================================
echo  OpenClaw restart launched in separate window.
echo  Check outputs\run_everything.log for full transcript.
echo ============================================================
echo.
pause
endlocal
