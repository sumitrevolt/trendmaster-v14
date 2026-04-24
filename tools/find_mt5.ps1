$ErrorActionPreference = 'SilentlyContinue'

# Check known install roots
$roots = @(
    'C:\',
    'C:\Program Files',
    'C:\Program Files (x86)'
)
$found = @()
foreach($r in $roots){
    if(Test-Path $r){
        Get-ChildItem -Path $r -Directory | ForEach-Object {
            if($_.Name -match 'MetaTrader|Octa|MT5|Exness|FX'){
                $found += $_.FullName
            }
        }
    }
}

# Scan each candidate for terminal64.exe and metaeditor64.exe
foreach($d in $found){
    $t = Join-Path $d 'terminal64.exe'
    $m = Join-Path $d 'metaeditor64.exe'
    if((Test-Path $t) -or (Test-Path $m)){
        Write-Output ("DIR:  " + $d)
        if(Test-Path $t){ Write-Output ("  terminal64: " + $t) }
        if(Test-Path $m){ Write-Output ("  metaeditor: " + $m) }
    }
}

# Also try the MetaQuotes data folder to learn terminal IDs
$mq = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
if(Test-Path $mq){
    Write-Output ""
    Write-Output "MetaQuotes terminals:"
    Get-ChildItem $mq -Directory | ForEach-Object {
        Write-Output ("  " + $_.Name)
    }
}

# And origin.txt for each
if(Test-Path $mq){
    Write-Output ""
    Write-Output "Terminal origin.txt pointers:"
    Get-ChildItem $mq -Directory | ForEach-Object {
        $o = Join-Path $_.FullName 'origin.txt'
        if(Test-Path $o){
            $txt = Get-Content $o -Raw
            Write-Output ("  " + $_.Name + " -> " + $txt.Trim())
        }
    }
}
