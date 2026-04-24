@echo off
REM =======================================================================
REM  tools\install_scheduled_rebuild.cmd
REM
REM  Registers a Windows Task Scheduler entry that runs
REM  tools\scheduled_rebuild.cmd daily at 3:00 AM local time. Idempotent
REM  — uses /F to overwrite any existing task with the same name.
REM
REM  To remove:   schtasks /Delete /TN "TrendMaster Code Graph Rebuild" /F
REM  To inspect: schtasks /Query /TN "TrendMaster Code Graph Rebuild" /V /FO LIST
REM =======================================================================
setlocal
pushd "%~dp0\.."

set "TASK=TrendMaster Code Graph Rebuild"
set "CMD=%CD%\tools\scheduled_rebuild.cmd"

if not exist "%CMD%" (
    echo [install_scheduled_rebuild] ERROR: %CMD% not found.
    popd
    exit /b 1
)

schtasks /Create /F /TN "%TASK%" /SC DAILY /ST 03:00 /TR "\"%CMD%\"" >nul
if errorlevel 1 (
    echo [install_scheduled_rebuild] schtasks /Create failed.
    popd
    exit /b 1
)

echo [install_scheduled_rebuild] Registered task: %TASK%
echo                              Runs daily at 03:00 local time.
echo                              Log: %CD%\logs\code_review_graph_rebuild.log

popd
endlocal
