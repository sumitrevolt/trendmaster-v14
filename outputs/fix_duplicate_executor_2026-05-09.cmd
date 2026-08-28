@echo off
REM Surgical fix for duplicate python_signal_executor.py processes.
REM Kills only executors (NOT brain, NOT webhook, NOT trailing-stop).
REM Deletes orphan lock file. Spawns one clean instance. Verifies heartbeat.

cd /d "%~dp0\.."

echo.
echo This will:
echo   1. Kill ALL python_signal_executor.py processes (currently 2 detected)
echo   2. Delete orphaned lock file
echo   3. Spawn ONE clean executor
echo   4. Verify heartbeat
echo.
echo Brain, TV webhook, trailing-stop, watchdog are NOT touched.
echo.
set /p CONFIRM="Proceed? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo Aborted.
    pause
    exit /b 0
)

"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\fix_duplicate_executor_2026-05-09.py"
echo.
pause
