$p = Get-CimInstance Win32_Process -Filter "ProcessId=2276" | Select-Object ProcessId, Name, CommandLine
if ($p) {
    Write-Host "PID: $($p.ProcessId)"
    Write-Host "Name: $($p.Name)"
    Write-Host "CommandLine: $($p.CommandLine)"
} else {
    Write-Host "PID 2276 not found"
}

# Also check all python.exe processes for brain-like command lines
Write-Host ""
Write-Host "=== All python.exe processes ==="
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
    Write-Host "PID=$($_.ProcessId)  CMD=$($_.CommandLine)"
}
