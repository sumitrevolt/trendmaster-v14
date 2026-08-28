@echo off
REM ============================================================================
REM   fix_popups_2026-05-08.cmd  —  silence ALL recurring scheduled tasks
REM
REM   Cause: several schtasks were registered to run a .cmd file directly.
REM   Windows Task Scheduler runs .cmd through cmd.exe, which flashes a
REM   console window every time even when the script's body is silent.
REM   Switching the action to wscript.exe + .vbs (with WScript.Shell.Run
REM   show=0) executes truly hidden — no flash.
REM
REM   This script re-registers each chronic-popup task to use the corresponding
REM   hidden_*.vbs wrapper that's already in tools\.
REM
REM   Tasks fixed:
REM     - TrendMaster TV Webhook Watchdog       (every 5 min)
REM     - TrendMaster Process Watchdog          (every 1 min)
REM     - TrendMaster Zero Trades Watchdog      (daily 09:00)
REM     - TrendMaster Health Watchdog           (every 1 min — already silent,
REM                                              re-applied for safety)
REM     - TrendMaster Master Autostart          (ONLOGON — already silent,
REM                                              re-applied for safety)
REM ============================================================================
setlocal
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

set "PYW=C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\pythonw.exe"
set "VBS_DIR=C:\Users\Ratanshila\Documents\autmated trading\tools"

echo.
echo ============================================================
echo   1/5  TV Webhook Watchdog  (every 5 min)
echo ============================================================
set "TASK=TrendMaster TV Webhook Watchdog"
set "VBS=%VBS_DIR%\hidden_tv_webhook_watchdog.vbs"
if not exist "%VBS%" (
    echo  [X] %VBS% missing — cannot register hidden version
) else (
    schtasks /Delete /TN "%TASK%" /F >nul 2>&1
    schtasks /Create /TN "%TASK%" /TR "wscript.exe \"%VBS%\"" /SC MINUTE /MO 5 /RL LIMITED /F
    if errorlevel 1 (echo  [X] failed to install %TASK%) else (echo  [OK] %TASK% silent via VBS)
)

echo.
echo ============================================================
echo   2/5  Process Watchdog  (every 1 min)
echo ============================================================
set "TASK=TrendMaster Process Watchdog"
set "VBS=%VBS_DIR%\hidden_process_watchdog.vbs"
if not exist "%VBS%" (
    echo  [!] %VBS% missing — registering with pythonw.exe directly
    schtasks /Delete /TN "%TASK%" /F >nul 2>&1
    schtasks /Create /TN "%TASK%" /TR "\"%PYW%\" \"%VBS_DIR%\process_watchdog.py\"" /SC MINUTE /MO 1 /RL LIMITED /F
) else (
    schtasks /Delete /TN "%TASK%" /F >nul 2>&1
    schtasks /Create /TN "%TASK%" /TR "wscript.exe \"%VBS%\"" /SC MINUTE /MO 1 /RL LIMITED /F
    if errorlevel 1 (echo  [X] failed to install %TASK%) else (echo  [OK] %TASK% silent via VBS)
)

echo.
echo ============================================================
echo   3/5  Zero Trades Watchdog  (daily 09:00)
echo ============================================================
set "TASK=TrendMaster Zero Trades Watchdog"
set "VBS=%VBS_DIR%\hidden_zero_trades_watchdog.vbs"
if not exist "%VBS%" (
    echo  [!] %VBS% missing — registering with pythonw.exe directly
    schtasks /Delete /TN "%TASK%" /F >nul 2>&1
    schtasks /Create /TN "%TASK%" /TR "\"%PYW%\" \"%VBS_DIR%\zero_trades_watchdog.py\"" /SC DAILY /ST 09:00 /RL LIMITED /F
) else (
    schtasks /Delete /TN "%TASK%" /F >nul 2>&1
    schtasks /Create /TN "%TASK%" /TR "wscript.exe \"%VBS%\"" /SC DAILY /ST 09:00 /RL LIMITED /F
    if errorlevel 1 (echo  [X] failed to install %TASK%) else (echo  [OK] %TASK% silent via VBS)
)

echo.
echo ============================================================
echo   4/5  Health Watchdog  (every 1 min — re-applied for safety)
echo ============================================================
set "TASK=TrendMaster Health Watchdog"
set "SCRIPT=%VBS_DIR%\health_watchdog.py"
schtasks /Delete /TN "%TASK%" /F >nul 2>&1
schtasks /Create /TN "%TASK%" /TR "\"%PYW%\" \"%SCRIPT%\" --once" /SC MINUTE /MO 1 /RL LIMITED /F
if errorlevel 1 (echo  [X] failed to install %TASK%) else (echo  [OK] %TASK% silent via pythonw.exe)

echo.
echo ============================================================
echo   5/5  Master Autostart  (ONLOGON — re-applied for safety)
echo ============================================================
set "TASK=TrendMaster Master Autostart"
set "SCRIPT=%VBS_DIR%\master_autostart.py"
schtasks /Delete /TN "%TASK%" /F >nul 2>&1
schtasks /Create /TN "%TASK%" /TR "\"%PYW%\" \"%SCRIPT%\"" /SC ONLOGON /F
if errorlevel 1 (echo  [X] failed to install %TASK%) else (echo  [OK] %TASK% silent via pythonw.exe)

echo.
echo ============================================================
echo   VERIFY  —  list all silent task actions
echo ============================================================
echo.
for %%T in (
    "TrendMaster TV Webhook Watchdog"
    "TrendMaster Process Watchdog"
    "TrendMaster Zero Trades Watchdog"
    "TrendMaster Health Watchdog"
    "TrendMaster Master Autostart"
) do (
    echo --- %%T ---
    schtasks /Query /TN %%T /FO LIST 2>nul | findstr /C:"Task To Run" /C:"Status"
    echo.
)

echo ============================================================
echo   DONE — popups should stop within the next 5 minutes.
echo ============================================================
echo.
echo  If you STILL see a flash every minute, run this to find the culprit:
echo    schtasks /Query /FO LIST ^| findstr /I /C:"TrendMaster" /C:"Run:"
echo.
endlocal
