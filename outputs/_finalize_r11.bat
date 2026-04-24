@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_finalize_r11.out" 2>&1
exit /b
:run
echo ===killing duplicate brain 15952 (venv one that failed to get lock)===
powershell -NoProfile -Command "Stop-Process -Id 15952 -Force -ErrorAction SilentlyContinue"
timeout /t 3 /nobreak >nul
echo ===LIVE PROCS===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'name=\"python.exe\"' | Select-Object ProcessId, @{n='Cmd';e={$_.CommandLine}} | Format-Table -AutoSize -Wrap"
echo ===LIVE BUY/SELL SIGNALS===
powershell -NoProfile -Command "$files = Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files' -Filter 'trendmaster_signals_*.json'; foreach ($f in $files) { $c = Get-Content $f.FullName -Raw; if ($c -match '\"direction\":\"(BUY|SELL)\"') { Write-Host ($f.Name + ' -> ' + $matches[1] + ' | ' + $c.Substring(0,[Math]::Min(250,$c.Length))) } }"
echo ===MT5 EXPERTS LOG (last 15 lines)===
powershell -NoProfile -Command "$f = Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Logs\*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Write-Host ('Latest: ' + $f.Name + ' modified ' + $f.LastWriteTime); Get-Content $f.FullName -Tail 15"
echo ===BRAIN TICK SUMMARY (last 10)===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 10 | Where-Object { $_ -match 'tick_all|veto' }"
