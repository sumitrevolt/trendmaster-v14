@echo off
REM ============================================================================
REM  restart_executor_FIX_2026-05-09.cmd
REM
REM  THE one-line bug that caused 5 days of "no trades":
REM    tools/python_signal_executor.py ALLOWED_STRATEGIES did NOT include
REM    "local_generator".  Local signal generator was firing 76 signals/run
REM    that the executor SILENTLY DROPPED.
REM
REM  Patch applied 2026-05-09 00:30 IST.  This script restarts the executor
REM  so the patch takes effect, then verifies fresh log output proves it.
REM ============================================================================
setlocal
cd /d "D:\autmated trading"

echo.
echo ============================================================
echo   STEP 1 -  Killing all python_signal_executor processes
echo ============================================================
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | ForEach-Object { Write-Host ('    PID ' + $_.ProcessId); taskkill /F /PID $_.ProcessId 2>$null }"

echo  - clearing singleton lock
del /f /q logs\python_signal_executor.lock 2>nul

echo  - waiting 4 seconds for OS to release file handles
ping 127.0.0.1 -n 5 >nul

echo.
echo ============================================================
echo   STEP 2 -  Starting fresh executor with the patch
echo ============================================================
start "TM Executor - LIVE (patched 2026-05-09)" /MIN cmd /c "title TM Executor - LIVE && cd /d D:\autmated trading && .venv\Scripts\python.exe -u tools\python_signal_executor.py 1>> logs\python_signal_executor.out 2>> logs\python_signal_executor.err"

echo  - waiting 8s for startup
ping 127.0.0.1 -n 9 >nul

echo.
echo ============================================================
echo   STEP 3 -  Verify executor is alive AND processing signals
echo ============================================================
echo  - process check
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Select-Object ProcessId, @{N='start';E={$_.CreationDate}} | Format-Table"

echo  - last 15 lines of executor log (should show recent heartbeat)
powershell -NoProfile -Command "Get-Content 'logs\python_signal_executor.log' -Tail 15"
echo.
echo  - looking for the new diagnostic line 'tv_strategy=...not in ALLOWED_STRATEGIES'
echo    (will appear next tick if any non-whitelisted signal lands)
echo.

echo ============================================================
echo   STEP 4 -  Trigger fresh local_generator run
echo ============================================================
echo  Generates a fresh batch of signals so we see them get processed.
echo  Then executor next tick will pick them up.
echo.
.venv\Scripts\python.exe tools\local_signal_generator.py 2>nul
if errorlevel 1 (
    echo  [INFO] local_signal_generator.py exited non-zero or not found - that's OK
    echo  if its own schtask is running.  Existing signal files in MT5 dir will be
    echo  picked up on next executor tick anyway.
)

echo.
echo  - waiting 12s for executor to process new signals
ping 127.0.0.1 -n 13 >nul

echo.
echo ============================================================
echo   STEP 5 -  Final check  -  did trades fire?
echo ============================================================
echo  - searching log for 'ORDER PLACED' or skip-reason lines
powershell -NoProfile -Command "Get-Content 'logs\python_signal_executor.log' -Tail 30 | Select-String -Pattern 'ORDER PLACED|skip|SAFEGUARD|placed_this_round'"
echo.
echo  - current open MT5 positions
powershell -NoProfile -Command "Get-Content 'logs\python_signal_executor.log' -Tail 50 | Select-String -Pattern 'open_positions=' | Select-Object -Last 3"

echo.
echo ============================================================
echo  DONE
echo ============================================================
echo.
echo  IF you see 'ORDER PLACED' lines above -- the fix worked. Trades fire.
echo.
echo  IF you see 'placed_this_round=0' but skip lines -- check the skip reason:
echo    - 'in cooldown'        = signal already traded recently (300s window)
echo    - 'already have ... position' = same direction already open
echo    - 'SAFEGUARD BLOCK'    = concentration cap or news blackout
echo    - 'weak confidence'    = conf below threshold (default 0.55)
echo.
echo  Watch live for 5 min:
echo    powershell -Command "Get-Content 'logs\python_signal_executor.log' -Tail 5 -Wait"
echo.
pause
endlocal
