$src = "C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_indicator_engine.py"
$bak = "C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_indicator_engine.py.bak"

if (Test-Path $src) {
    Copy-Item $src $bak -Force
    Write-Host "BACKUP OK: $bak"
} else {
    Write-Host "FILE NOT FOUND: $src"
}

Get-ChildItem "C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\" -Filter "*.py" |
    Select-Object Name, LastWriteTime, Length |
    Format-Table -AutoSize
