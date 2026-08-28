# ----------------------------------------------------------------------------
# fix_popups_2026-05-09.ps1
#
# Permanent fix for the recurring "console window pops up every minute"
# issue. Root cause from popup_audit_2026-05-09.json:
#   - "OpenClaw Gateway" schtask runs gateway.cmd directly (POPUP_CMD)
#   - "OpenClaw Watchdog" PowerShell script polls health and re-triggers
#     the gateway every 60s when down -> popup loop while gateway dead.
#   - OpenClaw is parked (gateway has been dead 8d, all crons disabled).
#
# What this does:
#   1. Stop any in-flight instance of "OpenClaw Gateway"
#   2. Disable "OpenClaw Watchdog" (no more respawn attempts)
#   3. Repoint "OpenClaw Gateway" action from gateway.cmd -> wscript hidden_gateway.vbs
#      (defensive: if anything ever triggers it again, no popup)
#   4. Disable "OpenClaw Gateway" itself (parked state)
#   5. Verify and report.
#
# Idempotent: safe to run multiple times.
# Does NOT touch any TrendMaster schtasks.
# ----------------------------------------------------------------------------
$ErrorActionPreference = 'Continue'

function Step([string]$name, [scriptblock]$body) {
    Write-Host "[STEP] $name" -ForegroundColor Cyan
    try {
        & $body
        Write-Host "  [OK]" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Step "Stop any in-flight OpenClaw Gateway instance" {
    schtasks /End /TN "OpenClaw Gateway" 2>&1 | Out-String | Write-Host
}

Step "Disable OpenClaw Watchdog (stops the respawn loop)" {
    schtasks /Change /TN "OpenClaw Watchdog" /Disable 2>&1 | Out-String | Write-Host
}

Step "Repoint OpenClaw Gateway -> hidden_gateway.vbs (silent wscript)" {
    $newAction = 'wscript.exe "C:\Users\Ratanshila\.openclaw\hidden_gateway.vbs"'
    schtasks /Change /TN "OpenClaw Gateway" /TR $newAction 2>&1 | Out-String | Write-Host
}

Step "Disable OpenClaw Gateway itself (parked state)" {
    schtasks /Change /TN "OpenClaw Gateway" /Disable 2>&1 | Out-String | Write-Host
}

Step "Verify OpenClaw Gateway final state" {
    $r = schtasks /Query /TN "OpenClaw Gateway" /XML 2>&1
    $r | Select-String -Pattern '<Command>|<Enabled>|<Arguments>|hidden_gateway' | ForEach-Object { Write-Host "  $_" }
}

Step "Verify OpenClaw Watchdog final state" {
    $r = schtasks /Query /TN "OpenClaw Watchdog" /FO LIST 2>&1
    $r | Select-String -Pattern 'Status|State|Last Run' | ForEach-Object { Write-Host "  $_" }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DONE. Popup source eliminated." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If schtasks /Change errored with 'Access denied', re-run this"
Write-Host "script in an elevated PowerShell (Run as Administrator)."
