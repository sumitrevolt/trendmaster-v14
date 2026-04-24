@echo off
REM Stop any running brain, then restart with the new R4 features.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo [i] Killing any existing brain ...
if exist logs\brain.pid (
    set /p STALE=<logs\brain.pid
    if not "%STALE%"=="" (
        taskkill /PID %STALE% /F /T >nul 2>&1
    )
    del /q logs\brain.pid >nul 2>&1
)

REM Kill any lingering python running the brain.
for /f "tokens=2" %%p in ('tasklist /fi "IMAGENAME eq python.exe" /fo CSV ^| findstr /i python') do (
    set PYPID=%%~p
    REM Only kill python.exe we can confirm — skip for safety.
)

timeout /t 2 /nobreak >nul

echo [i] Starting brain in new window ...
start "TrendMaster Brain - LIVE (do not close to keep trading)" cmd /k "title TrendMaster Brain - LIVE && python -u ai_trading_agents\trend_master_brain.py 2> logs\trend_master_brain.err"

timeout /t 5 /nobreak >nul

echo [i] Capturing PID ...
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object -First 1; if ($p) { $p.ProcessId | Out-File 'logs\brain.pid' -Encoding ascii; Write-Host ('Brain PID: ' + $p.ProcessId) } else { Write-Host 'PID capture failed.' }"

echo.
echo [i] Checking live log tail ...
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "Get-Content logs\trend_master_brain.log -Tail 5"

echo.
echo [i] Brain restarted. Use /status /perf /digest /gates on Telegram.
