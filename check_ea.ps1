$f = 'C:\Users\Ratanshila\Documents\autmated trading\AI_SUPERBB_v14_TrendMaster.mq5'
$c = Get-Content $f -Raw
$lines = (Get-Content $f).Count
$opens = ($c.ToCharArray() | Where-Object { $_ -eq '{' }).Count
$closes = ($c.ToCharArray() | Where-Object { $_ -eq '}' }).Count
Write-Host ("Lines: " + $lines + "  Opens: " + $opens + "  Closes: " + $closes + "  Diff: " + ($opens - $closes))
Write-Host '--- last 6 lines ---'
Get-Content $f -Tail 6
