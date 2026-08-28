$paths = @(
    'C:\Program Files\MetaTrader 5',
    'C:\Program Files (x86)\MetaTrader 5',
    'C:\Users\Ratanshila\AppData\Local\Programs\MetaTrader 5',
    'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes'
)
foreach ($p in $paths) {
    if (Test-Path $p) {
        Write-Host "== $p =="
        Get-ChildItem $p -Filter 'meta*.exe' -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 5 -Property FullName, Length |
            ForEach-Object { Write-Host ("  " + $_.FullName + "  " + $_.Length + " bytes") }
    }
}

# Look at running terminal64.exe for its path
Get-CimInstance Win32_Process -Filter "Name='terminal64.exe'" | ForEach-Object {
    Write-Host ""
    Write-Host "terminal64.exe path: $($_.ExecutablePath)"
    $dir = Split-Path $_.ExecutablePath
    Write-Host "siblings:"
    Get-ChildItem $dir -Filter 'meta*' -File | ForEach-Object {
        Write-Host ("  " + $_.Name + "  " + $_.Length + " bytes")
    }
}
