@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_mt5_check.out" 2>&1
exit /b
:run
echo ===MT5 PROCESSES===
tasklist /FI "IMAGENAME eq terminal64.exe" /NH /FO CSV
tasklist /FI "IMAGENAME eq terminal.exe" /NH /FO CSV
tasklist /FI "IMAGENAME eq metatrader64.exe" /NH /FO CSV
echo.
echo ===MT5 LAST LOG WRITE TIMES (today)===
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Logs\20260423.log' -ErrorAction SilentlyContinue | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize"
powershell -NoProfile -Command "Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\Logs\20260423.log' -ErrorAction SilentlyContinue | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize"
echo.
echo ===USDJPY SIGNAL FILE (the pair brain is saying BUY on)===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_USDJPY.json' -ErrorAction SilentlyContinue"
echo.
echo ===TERMINAL LOG TAIL (MT5 terminal-level events)===
powershell -NoProfile -Command "$f = Get-ChildItem 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\Logs\*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Write-Host ('Latest log: ' + $f.Name + ' modified ' + $f.LastWriteTime); Get-Content $f.FullName -Tail 30"
