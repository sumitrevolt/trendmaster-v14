@echo off
REM ============================================================================
REM admin_finish_popup_fix_2026-05-09.cmd  --  Run as Administrator
REM
REM This finishes the popup fix that needed admin rights:
REM   - Disable "OpenClaw Gateway" schtask (cannot be done as normal user)
REM   - Confirms "OpenClaw Watchdog" is disabled (was done already as user)
REM
REM What's already in place (no admin needed):
REM   - All 7 OpenClaw cron jobs disabled in ~/.openclaw/cron/jobs.json
REM   - gateway.cmd replaced with a no-op exit (was popping a cmd window
REM     every minute via the watchdog respawn loop)
REM   - Watchdog already disabled (confirmed via subprocess earlier)
REM
REM After this script: zero popups, ever, even on next logon.
REM
REM Right-click this file -> Run as administrator
REM ============================================================================

echo.
echo Disabling "OpenClaw Gateway" schtask...
schtasks /Change /TN "OpenClaw Gateway" /Disable
if %errorlevel% neq 0 (
    echo [X] FAILED - this script must be Run as Administrator
    pause
    exit /b 1
)
echo.

echo Disabling "OpenClaw Watchdog" schtask (idempotent)...
schtasks /Change /TN "OpenClaw Watchdog" /Disable

echo.
echo Verifying...
schtasks /Query /TN "OpenClaw Gateway"  /FO LIST | findstr /i "Status Scheduled"
schtasks /Query /TN "OpenClaw Watchdog" /FO LIST | findstr /i "Status Scheduled"

echo.
echo ============================================================
echo   DONE -- no popups ever again
echo ============================================================
echo.
pause
