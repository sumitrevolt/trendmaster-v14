# Check all known sources of auto-respawn for trend_master_brain.py

Write-Output "=== TASK SCHEDULER tasks containing 'python' or 'trend' ==="
try {
    Get-ScheduledTask | Where-Object {
        ($_.Actions | Where-Object {
            ($_.Execute -ne $null -and ($_.Execute -like '*python*' -or $_.Execute -like '*trend*')) -or
            ($_.Arguments -ne $null -and ($_.Arguments -like '*trend_master*' -or $_.Arguments -like '*autmated*'))
        })
    } | ForEach-Object {
        $a = $_.Actions[0]
        Write-Output ("PATH={0}`tNAME={1}`tEXE={2}`tARGS={3}" -f $_.TaskPath, $_.TaskName, $a.Execute, $a.Arguments)
    }
} catch {
    Write-Output "Get-ScheduledTask error: $_"
}

Write-Output ""
Write-Output "=== HKCU Run keys ==="
try {
    Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -ErrorAction SilentlyContinue |
        ForEach-Object { $_.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object { Write-Output ("$($_.Name) = $($_.Value)") } }
} catch {}

Write-Output ""
Write-Output "=== HKLM Run keys ==="
try {
    Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run" -ErrorAction SilentlyContinue |
        ForEach-Object { $_.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object { Write-Output ("$($_.Name) = $($_.Value)") } }
} catch {}

Write-Output ""
Write-Output "=== HKCU Startup folder contents ==="
$startup = [Environment]::GetFolderPath('Startup')
Write-Output "Path: $startup"
Get-ChildItem -Path $startup -Force -ErrorAction SilentlyContinue | ForEach-Object { Write-Output $_.FullName }

Write-Output ""
Write-Output "=== Common Startup folder contents ==="
$cstart = [Environment]::GetFolderPath('CommonStartup')
Write-Output "Path: $cstart"
Get-ChildItem -Path $cstart -Force -ErrorAction SilentlyContinue | ForEach-Object { Write-Output $_.FullName }

Write-Output ""
Write-Output "=== Windows Services with python in path ==="
Get-CimInstance Win32_Service | Where-Object { $_.PathName -ne $null -and ($_.PathName -like '*python*' -or $_.PathName -like '*trend_master*' -or $_.PathName -like '*autmated*') } |
    ForEach-Object { Write-Output ("SERVICE={0}`tSTATE={1}`tPATH={2}" -f $_.Name, $_.State, $_.PathName) }

Write-Output ""
Write-Output "=== DONE ==="
