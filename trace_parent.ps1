# Walk parent chain for any python brain process
$pythonProcs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -ne $null -and $_.CommandLine -like '*trend_master_brain*'
}

foreach ($p in $pythonProcs) {
    Write-Output "================================================================"
    Write-Output ("BRAIN PID={0}" -f $p.ProcessId)
    Write-Output ("CMD: {0}" -f $p.CommandLine)
    $cur = $p
    $depth = 0
    while ($cur -ne $null -and $depth -lt 8) {
        Write-Output ("  [{0}] PID={1} NAME={2} CMD={3}" -f $depth, $cur.ProcessId, $cur.Name, $cur.CommandLine)
        $parentId = $cur.ParentProcessId
        if (-not $parentId) { break }
        $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue
        $depth++
    }
}

Write-Output ""
Write-Output "================================================================"
Write-Output "ALL cmd.exe processes (parent chain too):"
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' } | ForEach-Object {
    Write-Output ("PID={0} PPID={1} CMD={2}" -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine)
}
