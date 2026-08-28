@echo off
set OUT=C:\Users\Ratanshila\Documents\autmated trading\outputs\brain_status.log
echo [%DATE% %TIME%] brain status check > "%OUT%"

echo. >> "%OUT%"
echo === brain.lock file === >> "%OUT%"
if exist "C:\Users\Ratanshila\Documents\autmated trading\logs\brain.lock" (
    type "C:\Users\Ratanshila\Documents\autmated trading\logs\brain.lock" >> "%OUT%" 2>&1
) else (
    echo "no brain.lock" >> "%OUT%"
)

echo. >> "%OUT%"
echo === MT5 process === >> "%OUT%"
tasklist /FI "IMAGENAME eq terminal64.exe" >> "%OUT%" 2>&1

echo. >> "%OUT%"
echo === Python processes (looking for trend_master_brain) === >> "%OUT%"
tasklist /FI "IMAGENAME eq python.exe" /v 2>&1 | findstr /i "trend\|trading\|brain" >> "%OUT%" 2>&1
echo (empty = no brain Python running) >> "%OUT%"

echo. >> "%OUT%"
echo === Latest brain.log line === >> "%OUT%"
if exist "C:\Users\Ratanshila\Documents\autmated trading\logs\trend_master_brain.log" (
    powershell -command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\trend_master_brain.log' -Tail 5" >> "%OUT%" 2>&1
) else (
    echo "no brain.log" >> "%OUT%"
)

echo. >> "%OUT%"
echo === Brain state (last_signal_per_symbol count) === >> "%OUT%"
if exist "C:\Users\Ratanshila\Documents\autmated trading\logs\brain_state.json" (
    powershell -command "$state = Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\brain_state.json' | ConvertFrom-Json; 'last_signal_per_symbol entries: ' + $state.last_signal_per_symbol.PSObject.Properties.Count; 'halted: ' + $state.halted; 'trading_paused: ' + $state.trading_paused; 'restart_count: ' + $state.restart_count" >> "%OUT%" 2>&1
)

echo [%DATE% %TIME%] done >> "%OUT%"
