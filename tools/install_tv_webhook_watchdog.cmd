@echo off
REM =======================================================================
REM  tools\install_tv_webhook_watchdog.cmd
REM
REM  Registers a Windows Task Scheduler entry that runs
REM  tools\run_tv_webhook_watchdog.cmd every 5 minutes.
REM  Idempotent — uses /F to overwrite any existing task with the same name.
REM
REM  Why every 5 min: tunnel + receiver supervision needs to catch outages
REM  fast — the May-1→May-4 incident lost 72h of signals because nothing
REM  watched the receiver. Cost is trivial: each run is <1 s python + http.
REM
REM  To remove:   schtasks /Delete /TN "TrendMaster TV Webhook Watchdog" /F
REM  To inspect: schtasks /Query /TN "TrendMaster TV Webhook Watchdog" /V /FO LIST
REM  To run now: schtasks /Run    /TN "TrendMaster TV Webhook Watchdog"
REM =======================================================================
setlocal
pushd "%~dp0\.."

set "TASK=TrendMaster TV Webhook Watchdog"
set "CMD=%CD%\tools\run_tv_webhook_watchdog.cmd"

if not exist "%CMD%" (
    echo [install_tv_webhook_watchdog] ERROR: %CMD% not found.
    popd
    exit /b 1
)

REM /MO 5 = every 5 minutes; /SD today implicit; /ST 00:00 lets it run from boot.
schtasks /Create /F /TN "%TASK%" /SC MINUTE /MO 5 /ST 00:00 /TR "\"%CMD%\"" >nul
if errorlevel 1 (
    echo [install_tv_webhook_watchdog] schtasks /Create failed.
    popd
    exit /b 1
)

echo [install_tv_webhook_watchdog] Registered task: %TASK%
echo                                Runs every 5 minutes from system boot.
echo                                Log:    %CD%\logs\tv_webhook_watchdog.log
echo                                State:  %CD%\logs\tv_webhook_watchdog_state.json
echo.
echo To trigger a one-off run right now:
echo     schtasks /Run /TN "%TASK%"

popd
endlocal
