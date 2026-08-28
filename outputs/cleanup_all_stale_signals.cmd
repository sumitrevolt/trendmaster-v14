@echo off
REM Delete ALL stale signal JSON files in MT5 file dir.
REM Executor skips them every 5 sec — clogs logs + wastes CPU.

set MT5_DIR=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files

echo === Deleting stale signal files from MT5 dir ===
echo Path: %MT5_DIR%
echo.

REM Delete trendmaster_signals_*.json files older than 90 sec (executor's age limit)
REM Using powershell because cmd doesn't easily filter by mtime
powershell -NoProfile -Command "$dir = '%MT5_DIR%'; $cutoff = (Get-Date).AddSeconds(-90); Get-ChildItem $dir -Filter 'trendmaster_signals*.json' | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object { Write-Host '  delete' $_.Name '(' ([int]((Get-Date) - $_.LastWriteTime).TotalSeconds) 'sec stale )'; Remove-Item -Force $_.FullName }"

echo.
echo Done.
timeout /t 5 /nobreak > nul
