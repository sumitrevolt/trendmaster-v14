$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -or
    ($_.CommandLine -ne $null -and (
        $_.CommandLine -like '*trend_master*' -or
        $_.CommandLine -like '*TRENDMASTER*' -or
        $_.CommandLine -like '*main.py*' -or
        $_.CommandLine -like '*autmated trading*'
    ))
}
foreach ($p in $procs) {
    Write-Output ("PID={0}`tNAME={1}`tCMD={2}" -f $p.ProcessId, $p.Name, $p.CommandLine)
}
Write-Output "DONE"
