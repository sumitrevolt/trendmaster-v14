# Hard restart: kill ALL python.exe running trend_master_brain, then start fresh.
Set-Location 'C:\Users\Ratanshila\Documents\autmated trading'

Write-Host "[i] Finding brain python.exe processes..."
$brains = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
          Where-Object { $_.CommandLine -like '*trend_master_brain*' }
if ($brains) {
    Write-Host "[i] Found $($brains.Count) brain process(es); killing..."
    foreach ($p in $brains) {
        Write-Host "    killing PID $($p.ProcessId): $($p.CommandLine)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "[i] No running brain found."
}

# Also kill any cmd.exe wrappers titled "TrendMaster Brain".
$wrappers = Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
            Where-Object { $_.CommandLine -like '*trend_master_brain*' }
foreach ($w in $wrappers) {
    Write-Host "    killing wrapper PID $($w.ProcessId)"
    Stop-Process -Id $w.ProcessId -Force -ErrorAction SilentlyContinue
}

if (Test-Path logs\brain.pid) { Remove-Item -Force logs\brain.pid }

Start-Sleep -Seconds 2

Write-Host "[i] Starting fresh brain detached..."
$stdoutPath = "$(Get-Location)\logs\trend_master_brain.out"
$stderrPath = "$(Get-Location)\logs\trend_master_brain.err"
$proc = Start-Process -FilePath "python" `
    -ArgumentList @('-u', 'ai_trading_agents\trend_master_brain.py') `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru
$proc.Id | Out-File -FilePath logs\brain.pid -Encoding ascii
Write-Host "[OK] New brain PID: $($proc.Id)"

Start-Sleep -Seconds 6

Write-Host "[i] First 20 lines of new brain log:"
if (Test-Path logs\trend_master_brain.log) {
    Get-Content logs\trend_master_brain.log -Tail 5
}
if (Test-Path logs\trend_master_brain.out) {
    Write-Host "[i] stdout tail:"
    Get-Content logs\trend_master_brain.out -Tail 5
}
if (Test-Path logs\trend_master_brain.err) {
    $errContent = Get-Content logs\trend_master_brain.err -Tail 10
    if ($errContent) {
        Write-Host "[i] stderr tail:"
        $errContent
    }
}
