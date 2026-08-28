@echo off
REM ============================================================================
REM   fix_openclaw_popup_2026-05-08.cmd
REM
REM   The "openclaw-gateway" cmd window keeps flashing because the Windows
REM   scheduled task "OpenClaw Gateway" runs gateway.cmd directly (visible).
REM   A `hidden_gateway.vbs` already exists at C:\Users\Ratanshila\.openclaw\
REM   that uses WScript.Shell.Run with show=0 (truly hidden).
REM
REM   This re-registers the schtask to use the VBS wrapper.
REM ============================================================================
setlocal

set "TASK=OpenClaw Gateway"
set "VBS=C:\Users\Ratanshila\.openclaw\hidden_gateway.vbs"

echo.
echo ============================================================
echo   Step 1/4  -  Killing any running gateway processes
echo ============================================================
echo  - killing node.exe processes running openclaw gateway
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='node.exe'\" | Where-Object { $_.CommandLine -like '*openclaw*gateway*' -or $_.CommandLine -like '*--port 18789*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

echo  - killing any cmd.exe windows running gateway.cmd
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*gateway.cmd*' } | ForEach-Object { Write-Host '    PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"

echo.
echo ============================================================
echo   Step 2/4  -  Verifying hidden_gateway.vbs exists
echo ============================================================
if not exist "%VBS%" (
    echo  [X] %VBS% missing.  Cannot proceed.
    echo      Manual fix: re-register %TASK% to point at the right launcher.
    exit /b 2
)
echo  [OK] %VBS% present

echo.
echo ============================================================
echo   Step 3/4  -  Re-registering "%TASK%" to use VBS wrapper
echo ============================================================
echo  - deleting old task
schtasks /Delete /TN "%TASK%" /F >nul 2>&1

echo  - registering new task with wscript hidden VBS, ONLOGON
schtasks /Create /TN "%TASK%" /TR "wscript.exe \"%VBS%\"" /SC ONLOGON /F
if errorlevel 1 (
    echo  [X] schtasks /Create failed.
    exit /b 3
)

echo.
echo ============================================================
echo   Step 4/4  -  Verifying new task action
echo ============================================================
schtasks /Query /TN "%TASK%" /FO LIST /V > "%TEMP%\verify_oc.txt" 2>nul
findstr /C:"Task To Run" "%TEMP%\verify_oc.txt"
findstr /C:"Status"      "%TEMP%\verify_oc.txt"
echo.

echo  - starting gateway now (silent)
schtasks /Run /TN "%TASK%" >nul 2>&1
echo    issued /Run

echo.
echo ============================================================
echo   DONE - "%TASK%" will run silently from next logon onwards.
echo   Just-issued /Run started the gateway right now (no popup).
echo ============================================================
echo.
echo  Verify gateway is alive on port 18789:
echo    powershell -NoProfile -Command "Test-NetConnection -ComputerName 127.0.0.1 -Port 18789 ^| Select-Object TcpTestSucceeded"
echo.
endlocal
