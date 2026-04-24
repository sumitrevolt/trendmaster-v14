$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
$MT5  = "$env:APPDATA\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files"

Write-Output "================================================================"
Write-Output "1. BRAIN PROCESS STATUS"
Write-Output "================================================================"
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -ne $null -and $_.CommandLine -like '*trend_master_brain*'
} | ForEach-Object {
    Write-Output ("  PID={0,-6}  PPID={1,-6}  STARTED={2}  CMD={3}" -f $_.ProcessId, $_.ParentProcessId, $_.CreationDate, $_.CommandLine.Substring(0, [Math]::Min(120, $_.CommandLine.Length)))
}

Write-Output ""
Write-Output "================================================================"
Write-Output "2. BRAIN LOCK FILE"
Write-Output "================================================================"
$lockFile = Join-Path $ROOT "logs\brain.lock"
if (Test-Path $lockFile) {
    $lockPid = (Get-Content $lockFile -Raw -ErrorAction SilentlyContinue).Trim()
    Write-Output "  brain.lock contents: '$lockPid'"
    if ($lockPid) {
        try {
            $lockProc = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
            if ($lockProc) {
                Write-Output "  Lock PID is alive: $($lockProc.Name) (started $($lockProc.StartTime))"
            } else {
                Write-Output "  Lock PID $lockPid is DEAD (stale lock)"
            }
        } catch {
            Write-Output "  Could not check lock PID: $_"
        }
    }
} else {
    Write-Output "  brain.lock does not exist"
}

Write-Output ""
Write-Output "================================================================"
Write-Output "3. SIGNAL FILES IN MT5 (per-symbol JSONs)"
Write-Output "================================================================"
if (Test-Path $MT5) {
    $signalFiles = Get-ChildItem -Path $MT5 -Filter "trendmaster_signals*.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    Write-Output "  Found $($signalFiles.Count) signal files in $MT5"
    foreach ($f in $signalFiles) {
        $age = (Get-Date) - $f.LastWriteTime
        $ageStr = "{0:N0}s ago" -f $age.TotalSeconds
        try {
            $j = Get-Content $f.FullName -Raw | ConvertFrom-Json
            $sym = if ($j.symbol) { $j.symbol } else { "?" }
            $dir = if ($j.direction) { $j.direction } else { "?" }
            $conf = if ($j.confidence) { $j.confidence } else { 0 }
            $age2 = if ($j.timestamp) { (Get-Date) - (Get-Date $j.timestamp) } else { $null }
            Write-Output ("  {0,-45}  age={1,-12}  sym={2,-7}  dir={3,-6}  conf={4,5:F2}" -f $f.Name, $ageStr, $sym, $dir, $conf)
        } catch {
            Write-Output ("  {0,-45}  age={1,-12}  PARSE ERROR: {2}" -f $f.Name, $ageStr, $_.Exception.Message)
        }
    }
} else {
    Write-Output "  MT5 Files folder NOT FOUND: $MT5"
}

Write-Output ""
Write-Output "================================================================"
Write-Output "4. BRAIN STATE FILE (last_signal, recent_results, etc.)"
Write-Output "================================================================"
$stateFile = Join-Path $ROOT "logs\brain_state.json"
if (Test-Path $stateFile) {
    try {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
        Write-Output "  schema_version:    $($state.schema_version)"
        Write-Output "  trading_paused:    $($state.trading_paused)"
        Write-Output "  daily_pnl:         $($state.daily_pnl)"
        Write-Output "  daily_trades:      $($state.daily_trades)"
        Write-Output "  restart_count:     $($state.restart_count)"
        Write-Output "  drawdown_lockout:  $($state.drawdown_lockout_until)"
        Write-Output "  recent_results:    $(@($state.recent_results).Count) entries"
        if ($state.recent_results -and @($state.recent_results).Count -gt 0) {
            Write-Output "  Last 3 trade results:"
            @($state.recent_results) | Select-Object -Last 3 | ForEach-Object {
                Write-Output ("    {0}" -f ($_ | ConvertTo-Json -Compress))
            }
        }
        Write-Output "  last_veto_per_symbol:"
        if ($state.last_veto_per_symbol) {
            $state.last_veto_per_symbol.PSObject.Properties | ForEach-Object {
                Write-Output ("    {0,-8} -> {1}" -f $_.Name, $_.Value)
            }
        } else {
            Write-Output "    (none captured yet)"
        }
    } catch {
        Write-Output "  ERROR parsing state: $_"
    }
} else {
    Write-Output "  brain_state.json NOT FOUND"
}

Write-Output ""
Write-Output "================================================================"
Write-Output "5. MT5 TERMINAL RUNNING?"
Write-Output "================================================================"
$mt5Procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'terminal*' -or $_.Name -like 'metatrader*' }
if ($mt5Procs) {
    foreach ($p in $mt5Procs) {
        Write-Output ("  PID={0,-6}  NAME={1,-20}  STARTED={2}" -f $p.ProcessId, $p.Name, $p.CreationDate)
    }
} else {
    Write-Output "  NO MT5 terminal process found - EA cannot run!"
}

Write-Output ""
Write-Output "================================================================"
Write-Output "6. RECENT BRAIN LOG (last 25 lines)"
Write-Output "================================================================"
$logFile = Join-Path $ROOT "logs\trend_master_brain.out"
if (Test-Path $logFile) {
    Get-Content $logFile -Tail 25 | ForEach-Object { Write-Output "  $_" }
} else {
    Write-Output "  Log file not found"
}

Write-Output ""
Write-Output "================================================================"
Write-Output "7. EA EXPERT LOG (latest 25 lines)"
Write-Output "================================================================"
$mqlLogs = "$env:APPDATA\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Logs"
if (Test-Path $mqlLogs) {
    $latestLog = Get-ChildItem -Path $mqlLogs -Filter "*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestLog) {
        Write-Output "  Reading: $($latestLog.Name) (modified $($latestLog.LastWriteTime))"
        Get-Content $latestLog.FullName -Tail 25 | ForEach-Object { Write-Output "  $_" }
    } else {
        Write-Output "  No EA log files found"
    }
} else {
    Write-Output "  EA log folder not found"
}

Write-Output ""
Write-Output "================================================================"
Write-Output "DONE"
Write-Output "================================================================"
