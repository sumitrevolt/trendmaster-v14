# =====================================================================
#  install_desktop_icon.ps1 — clean, single-shortcut installer.
#  ---------------------------------------------------------------------
#  What it does (in order):
#    1. Scans the user's Desktop AND the Public Desktop for any old /
#       duplicate trading-bot shortcuts.
#    2. Backs them up to <project>\archive\desktop_shortcuts_backup\
#       and deletes them from the Desktop.
#    3. Installs ONE canonical shortcut:
#         "Sumit AI Trading System.lnk"  ->  START_TRENDMASTER_v14.bat
#    4. Prints a clean before/after report.
#
#  No admin rights required. Pure PowerShell + WScript.Shell COM.
# =====================================================================

[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\Users\Ratanshila\Documents\autmated trading",
    [string]$ShortcutName = "Sumit AI Trading System",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ---------- helpers --------------------------------------------------
function Write-Step($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    [..] $msg" -ForegroundColor Yellow }
function Write-Err2($msg)  { Write-Host "    [X]  $msg" -ForegroundColor Red }

# ---------- paths ----------------------------------------------------
$Desktop       = [Environment]::GetFolderPath("Desktop")
$PublicDesktop = "$env:PUBLIC\Desktop"
$Target        = Join-Path $ProjectRoot "START_TRENDMASTER_v14.bat"
$WorkDir       = $ProjectRoot
$IconFile      = "$env:SystemRoot\System32\shell32.dll, 137"   # generic gear icon
$BackupDir     = Join-Path $ProjectRoot "archive\desktop_shortcuts_backup"
$Stamp         = Get-Date -Format "yyyyMMdd_HHmmss"

# Patterns we treat as "trading-bot related" — duplicates of these get removed.
# These are case-insensitive substrings of the file name (without extension).
$KnownAliases = @(
    "Sumit AI Trading",
    "AMD Smart Money",
    "AMD Forex",
    "AMD Trading",
    "TrendMaster",
    "Trend Master",
    "AI SuperBB",
    "AI Trading System",
    "AI Trading Bot",
    "Forex Bot",
    "Gold Scalp",
    "MT5 AI",
    "Sumit Trading",
    "Sumit Bot",
    "START_TRENDMASTER",
    "START_AI_SWARM",
    "START_ALL"
)

# ---------- preflight ------------------------------------------------
Write-Step "Preflight"
if (-not (Test-Path $Target)) {
    Write-Err2 "Launcher not found at $Target"
    Write-Err2 "Make sure the project folder is correct, then re-run."
    exit 1
}
Write-Ok "Launcher exists: $Target"
if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }
Write-Ok "Backup dir ready: $BackupDir"

# ---------- scan -----------------------------------------------------
Write-Step "Scanning Desktop for trading-bot shortcuts"
$candidates = @()
foreach ($d in @($Desktop, $PublicDesktop)) {
    if (-not (Test-Path $d)) { continue }
    Get-ChildItem -Path $d -Filter "*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
        $name = [IO.Path]::GetFileNameWithoutExtension($_.Name)
        foreach ($alias in $KnownAliases) {
            if ($name -like "*$alias*") {
                $candidates += [pscustomobject]@{
                    Path        = $_.FullName
                    Name        = $_.Name
                    DesktopRoot = $d
                    Matched     = $alias
                }
                break
            }
        }
    }
}
if ($candidates.Count -eq 0) {
    Write-Warn2 "No existing trading shortcuts found — clean slate."
} else {
    Write-Host "    Found $($candidates.Count) shortcut(s):"
    $candidates | ForEach-Object {
        Write-Host ("       - {0}    [{1}]" -f $_.Name, $_.Matched)
    }
}

# ---------- back up + delete duplicates ------------------------------
Write-Step "Backing up + removing old/duplicate shortcuts"
$removed = 0
foreach ($c in $candidates) {
    try {
        $dest = Join-Path $BackupDir ("{0}__{1}" -f $Stamp, $c.Name)
        if ($DryRun) {
            Write-Warn2 "[dry-run] would back up + delete $($c.Path)"
        } else {
            Copy-Item -Path $c.Path -Destination $dest -Force
            Remove-Item -Path $c.Path -Force
            Write-Ok "removed $($c.Name) (backup: $([IO.Path]::GetFileName($dest)))"
            $removed++
        }
    } catch {
        Write-Err2 "could not remove $($c.Path): $_"
    }
}
Write-Host "    Removed $removed shortcut(s)."

# ---------- install ONE clean shortcut -------------------------------
Write-Step "Installing single canonical shortcut"
$LinkPath = Join-Path $Desktop "$ShortcutName.lnk"

if ($DryRun) {
    Write-Warn2 "[dry-run] would create $LinkPath -> $Target"
} else {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($LinkPath)
    $sc.TargetPath       = $Target
    $sc.Arguments        = ""
    $sc.WorkingDirectory = $WorkDir
    $sc.IconLocation     = $IconFile
    $sc.Description      = "Sumit AI Trading System — TrendMaster v14 launcher"
    $sc.WindowStyle      = 1
    $sc.Save()
    if (Test-Path $LinkPath) {
        Write-Ok "Created: $LinkPath"
        Write-Ok "Target : $Target"
    } else {
        Write-Err2 "Failed to create $LinkPath"
        exit 2
    }
}

# ---------- verification ---------------------------------------------
Write-Step "Final Desktop state"
$final = Get-ChildItem -Path $Desktop -Filter "*.lnk" -ErrorAction SilentlyContinue |
    Where-Object {
        $n = [IO.Path]::GetFileNameWithoutExtension($_.Name)
        $KnownAliases | Where-Object { $n -like "*$_*" }
    }
if ($final) {
    $final | ForEach-Object { Write-Host ("    - {0}" -f $_.Name) }
} else {
    Write-Warn2 "(no trading shortcuts on desktop)"
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  DONE. Sirf ek clean icon ab desktop par hai." -ForegroundColor Cyan
Write-Host "  Double-click '$ShortcutName' to start the trading system." -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
