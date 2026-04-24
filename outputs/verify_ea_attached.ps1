# Verify every symbol's EA attachment + trading readiness.
Set-Location 'C:\Users\Ratanshila\Documents\autmated trading'

$termDataRoot = 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075'
$logFile = Join-Path $termDataRoot 'MQL5\Logs\20260423.log'

Write-Host "======================================================================"
Write-Host "  EA ATTACHMENT VERIFICATION"
Write-Host "======================================================================"
Write-Host ""

# 1. Read experts log (UTF-16 LE).
if (Test-Path $logFile) {
    $size = (Get-Item $logFile).Length
    $age  = [int]((Get-Date) - (Get-Item $logFile).LastWriteTime).TotalSeconds
    Write-Host "[log]  $logFile"
    Write-Host "       size=$size bytes, last-mod=$age seconds ago"
    Write-Host ""
    $content = Get-Content $logFile -Encoding Unicode -Raw

    # Count initializations per symbol.
    $initMatches = [regex]::Matches($content, 'AI_SUPERBB_v14_TrendMaster\s+\(([^,]+),[^)]+\)\s+Initialized\s+(\w+)')
    Write-Host "[inits]  $($initMatches.Count) Initialized lines"
    $seen = @{}
    foreach ($m in $initMatches) {
        $sym = $m.Groups[1].Value
        if (-not $seen.ContainsKey($sym)) {
            $seen[$sym] = 1
        } else {
            $seen[$sym] += 1
        }
    }
    $seen.Keys | Sort-Object | ForEach-Object {
        Write-Host ("    OK  {0,-8}  init x{1}" -f $_, $seen[$_])
    }

    # Last few EA-related lines.
    Write-Host ""
    Write-Host "[last 15 EA-related lines]"
    $eaLines = $content -split "`r?`n" | Where-Object {
        $_ -match 'SUPERBB|TrendMaster|C1|C2|C3|TMv14|BUY|SELL|order_send|TrySendOrder'
    }
    $eaLines | Select-Object -Last 15 | ForEach-Object {
        Write-Host ("    " + $_.Substring([Math]::Max(0, $_.Length - 200)))
    }
} else {
    Write-Host "[log] missing: $logFile"
}

# 2. Any open positions?
Write-Host ""
Write-Host "[open positions]"
try {
    $py = 'C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe'
    & $py -c @"
import MetaTrader5 as mt5
mt5.initialize()
pos = mt5.positions_get()
if pos:
    for p in pos:
        side = 'BUY' if p.type == 0 else 'SELL'
        print(f'  {p.symbol:8s} {side} vol={p.volume} price={p.price_open} profit={p.profit:+.2f}')
else:
    print('  (none)')
ai = mt5.account_info()
if ai:
    print(f'  equity=${ai.equity:.2f}  free_margin=${ai.margin_free:.2f}')
mt5.shutdown()
"@
} catch {
    Write-Host "  MT5 python probe failed: $_"
}

Write-Host ""
Write-Host "======================================================================"
