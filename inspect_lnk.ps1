$lnkPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\AI_Revenue_Machine.lnk"
Write-Output "Inspecting: $lnkPath"
Write-Output "Exists: $(Test-Path $lnkPath)"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
Write-Output ""
Write-Output "TargetPath: $($lnk.TargetPath)"
Write-Output "Arguments: $($lnk.Arguments)"
Write-Output "WorkingDirectory: $($lnk.WorkingDirectory)"
Write-Output "Description: $($lnk.Description)"
Write-Output "WindowStyle: $($lnk.WindowStyle)"
Write-Output "IconLocation: $($lnk.IconLocation)"

Write-Output ""
Write-Output "=== ALL cmd.exe processes (look for watch loops) ==="
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' } |
    ForEach-Object {
        Write-Output ("PID={0}  CMD={1}" -f $_.ProcessId, $_.CommandLine)
    }
