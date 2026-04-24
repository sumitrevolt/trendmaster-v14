Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -or
    ($_.CommandLine -ne $null -and ($_.CommandLine -like '*trend_master*' -or $_.CommandLine -like '*MASTER_START*' -or $_.CommandLine -like '*start_trading_bot*' -or $_.CommandLine -like '*main.py*'))
} | Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine | Format-List
