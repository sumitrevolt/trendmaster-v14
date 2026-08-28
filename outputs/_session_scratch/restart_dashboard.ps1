Set-Location 'C:\Users\Ratanshila\Documents\autmated trading'

Write-Host "[i] Killing existing dashboard listeners on :8000..."
$lines = netstat -ano | Select-String ":8000 " | Select-String "LISTENING"
foreach ($l in $lines) {
    $pid_ = ($l.ToString().Trim() -split '\s+')[-1]
    Write-Host "    killing PID $pid_"
    Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
}

# Kill any tools\dashboard.py processes by command line.
$dashes = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
          Where-Object { $_.CommandLine -like '*tools\dashboard*' -or $_.CommandLine -like '*tools/dashboard*' }
foreach ($d in $dashes) {
    Write-Host "    killing dashboard PID $($d.ProcessId)"
    Stop-Process -Id $d.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

Write-Host "[i] Starting fresh dashboard..."
$out = "$(Get-Location)\logs\dashboard.out"
$err = "$(Get-Location)\logs\dashboard.err"
$proc = Start-Process -FilePath "python" `
    -ArgumentList @('-u', 'tools\dashboard.py') `
    -WindowStyle Hidden `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -PassThru
Write-Host "[OK] New dashboard PID: $($proc.Id)"

Start-Sleep -Seconds 5

Write-Host "[i] Probing /performance..."
try {
    $r = Invoke-WebRequest -UseBasicParsing 'http://localhost:8000/performance' -TimeoutSec 5
    Write-Host "status=$($r.StatusCode), first 300 chars:"
    Write-Host ($r.Content.Substring(0, [Math]::Min(300, $r.Content.Length)))
} catch { Write-Host "FAIL: $_.Exception.Message" }
