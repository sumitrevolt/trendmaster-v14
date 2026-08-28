@echo off
REM Install schtask "TrendMaster Brain Forensics" — every 30 sec, silent.
REM Captures memory/CPU/threads/handles to logs/brain_forensics.jsonl.
REM When brain dies silently, the LAST jsonl line shows state at death.

cd /d "%~dp0\.."

set TASK_NAME=TrendMaster Brain Forensics
set VBS_PATH=C:\Users\Ratanshila\Documents\autmated trading\tools\hidden_brain_forensics.vbs

echo Installing schtask: %TASK_NAME%
echo.

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo Task already exists - deleting old version
    schtasks /Delete /TN "%TASK_NAME%" /F
)

REM /SC MINUTE /MO 1 = every 1 minute (Windows minimum granularity for schtasks)
REM /RL LIMITED = run at user privilege (no UAC popup)
REM Use wscript with the .vbs to avoid console flash
schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "wscript.exe \"%VBS_PATH%\"" ^
    /SC MINUTE /MO 1 ^
    /RL LIMITED ^
    /F

if errorlevel 1 (
    echo [X] schtask install failed
    exit /b 1
)

echo.
echo [OK] %TASK_NAME% installed - sampling every 1 minute
echo.
echo To verify:
echo   schtasks /Query /TN "%TASK_NAME%" /fo LIST /v
echo.
echo Forensic log: logs\brain_forensics.jsonl  (1 line per sample)
echo To inspect after a crash:
echo   tools\.venv\Scripts\python.exe -c "import json; [print(json.loads(l)) for l in open('logs/brain_forensics.jsonl').readlines()[-20:]]"
echo.
pause
