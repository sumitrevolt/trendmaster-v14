@echo off
REM ============================================================
REM  Install Windows Scheduled Task: ea_parity nightly diff
REM
REM  Runs weekdays at 02:30 LOCAL time. On first run it seeds
REM  reports\ea_parity_baseline.json and every subsequent run
REM  diffs against it. Telegram alert fires if divergence
REM  exceeds thresholds in tools\ea_parity_nightly.py.
REM
REM  Run once as administrator: right-click -> Run as admin.
REM
REM  Uninstall:
REM    schtasks /delete /tn "TrendMaster EA Parity Nightly" /f
REM  Run now:
REM    schtasks /run /tn "TrendMaster EA Parity Nightly"
REM  Reseed baseline (after an intentional rule change):
REM    del reports\ea_parity_baseline.json
REM    schtasks /run /tn "TrendMaster EA Parity Nightly"
REM ============================================================
setlocal

set ROOT=%~dp0
set PY=%ROOT%.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo.
echo Installing nightly ea_parity task...
echo ROOT=%ROOT%
echo PY=%PY%
echo.

schtasks /create /f /sc weekly /d MON,TUE,WED,THU,FRI /st 02:30 ^
    /tn "TrendMaster EA Parity Nightly" ^
    /tr "cmd /c cd /d \"%ROOT%\" && \"%PY%\" tools\ea_parity_nightly.py >> logs\ea_parity_nightly.log 2>&1"
if errorlevel 1 (
    echo [X] ea_parity nightly task failed to register
    endlocal & exit /b 1
) else (
    echo [OK] ea_parity nightly task registered
)

echo.
echo == Current TrendMaster tasks ==
schtasks /query /fo LIST /tn "TrendMaster EA Parity Nightly" 2>nul | findstr /i "TaskName Next"

echo.
echo Done. First run will seed the baseline, subsequent runs diff against it.
echo To run immediately:
echo   schtasks /run /tn "TrendMaster EA Parity Nightly"
endlocal
