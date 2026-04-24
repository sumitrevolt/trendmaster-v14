@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_status_r11.out" 2>&1
exit /b
:run
timeout /t 25 /nobreak >nul
echo ===PROCS===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'name=\"python.exe\"' | Select-Object ProcessId, @{n='Cmd';e={$_.CommandLine}} | Format-Table -AutoSize -Wrap"
echo ===BOOT LOG (last 25 lines)===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 25"
echo ===ERR===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.err' -Tail 10 -ErrorAction SilentlyContinue"
echo ===USDJPY SIGNAL===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_USDJPY.json' -ErrorAction SilentlyContinue"
echo ===XBRUSD SIGNAL===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_XBRUSD.json' -ErrorAction SilentlyContinue"
echo ===XAGUSD SIGNAL===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_XAGUSD.json' -ErrorAction SilentlyContinue"
