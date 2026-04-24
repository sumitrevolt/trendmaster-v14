@echo off
REM ============================================================
REM  Defender exclusion installer.  RIGHT-CLICK -> Run as admin.
REM
REM  Adds the TrendMaster repo folder as a Windows Defender
REM  exclusion so trading code (especially .mq5 / .ex5 / .cmd
REM  helpers) cannot be false-positive quarantined.
REM
REM  Background: on 2026-04-24 during the zero-trades fix session,
REM  34 files under ai_trading_agents/ vanished from disk while the
REM  running brain still had them loaded in memory. Git restored
REM  them, but this exclusion is the permanent fix.
REM ============================================================
setlocal

set REPO=C:\Users\Ratanshila\Documents\autmated trading

echo Adding Defender exclusion for:
echo   %REPO%
echo.

powershell -NoProfile -Command "Add-MpPreference -ExclusionPath '%REPO%' -ErrorAction Stop"
if errorlevel 1 (
    echo [X] FAILED - did you right-click and pick 'Run as administrator'?
    pause
    exit /b 1
)

echo [OK] Exclusion added. Verifying...
powershell -NoProfile -Command "(Get-MpPreference).ExclusionPath | Where-Object { $_ -like '*autmated*' }"

echo.
echo Done.
pause
endlocal
