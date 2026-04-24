@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_verify_r11.out" 2>&1
exit /b
:run
echo ===PROCS===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'name=\"python.exe\"' | Select-Object ProcessId, @{n='Cmd';e={$_.CommandLine}} | Format-Table -AutoSize -Wrap"
echo ===BOOT LOG===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 15"
echo ===ERR===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.err' -Tail 10 -ErrorAction SilentlyContinue"
echo ===USDJPY SIGNAL===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_USDJPY.json'"
echo ===any BUY/SELL signals right now?===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 18 | ForEach-Object { $c = Get-Content $_.FullName -Raw; if ($c -match '\"direction\":\"(BUY|SELL)\"') { Write-Host ($_.Name + ' : ' + $matches[0]) } }"
