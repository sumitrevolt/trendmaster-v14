# Force MT5 to detect the .mq5 change by touching the file + waiting + watching log.
$src = 'C:\Users\Ratanshila\Documents\autmated trading\AI_SUPERBB_v14_TrendMaster.mq5'
$dst = 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\AI_SUPERBB_v14_TrendMaster.mq5'
$log = 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Logs\20260423.log'

Write-Host "[1] Copying .mq5 again (triggers MT5 file-change detect)..."
Copy-Item -Force $src $dst

Write-Host "[2] Touching .mq5 timestamp..."
(Get-Item $dst).LastWriteTime = Get-Date

Write-Host "[3] Also touching .ex5 for good measure..."
$ex5 = $dst.Replace('.mq5', '.ex5')
if (Test-Path $ex5) {
    (Get-Item $ex5).LastWriteTime = Get-Date
}

Write-Host "[4] Waiting 30 seconds for MT5 to detect + reload..."
Start-Sleep -Seconds 30

Write-Host "[5] Log tail (last 30 lines, UTF-16):"
if (Test-Path $log) {
    Get-Content $log -Encoding Unicode -Tail 30
} else {
    Write-Host "  log file not found"
}
