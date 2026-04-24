@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_diag_pipeline.out" 2>&1
exit /b
:run
echo ===BRAIN LOG TAIL (last 30 lines)===
powershell -NoProfile -Command "Get-Content 'logs\trend_master_brain.out' -Tail 30"
echo.
echo ===SIGNAL FILES (live content of BUY/SELL ones)===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object { Write-Host ('--- ' + $_.Name + ' (' + $_.LastWriteTime + ') ---'); Get-Content $_.FullName }"
echo.
echo ===MT5 EXPERTS LOG (latest, tail 50)===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Logs\*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Write-Host ('--- ' + $_.Name + ' ---'); Get-Content $_.FullName -Tail 50 }"
echo.
echo ===MT5 TERMINAL LOG (latest, tail 30)===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\Logs\*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Write-Host ('--- ' + $_.Name + ' ---'); Get-Content $_.FullName -Tail 30 }"
