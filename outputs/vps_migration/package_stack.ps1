# package_stack.ps1 - build trendmaster_stack.zip for VPS migration
# Run from repo root on the LOCAL machine:
#   powershell -NoProfile -ExecutionPolicy Bypass -File outputs\vps_migration\package_stack.ps1
# Excludes .venv / logs bulk / .git / worktrees. Includes persistent state
# (brain_state.json etc.) so the server resumes with the same risk counters.
$ErrorActionPreference = "Stop"
$Root   = (Get-Location).Path
$OutDir = Join-Path $Root "outputs\vps_migration"
$Stage  = Join-Path $OutDir "stage\trendmaster"
$Zip    = Join-Path $OutDir "trendmaster_stack.zip"

if (Test-Path $OutDir\stage) { Remove-Item -Recurse -Force $OutDir\stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

function Copy-ItemSafe($src, $dest) {
    Copy-Item -Path $src -Destination $dest -Recurse -Force
}

# 1. Brain package. NOTE: ai_trading_agents is a junction to D:\autmated trading\
#    Copy-Item resolves junctions to real files automatically.
Copy-ItemSafe "$Root\ai_trading_agents" $Stage
# 2. Tools (dashboard, executor, watchdogs, vbs launchers, write_brain_pid, etc.)
Copy-ItemSafe "$Root\tools" $Stage
# 3. Config incl. .env (Telegram token etc.) - zip must stay private!
Copy-ItemSafe "$Root\config" $Stage
# 4. Root startup / ops scripts
$rootScripts = @("*.cmd", "*.vbs", "*.bat", "requirements.txt", "AI_SUPERBB_v14_TrendMaster.mq5")
foreach ($pat in $rootScripts) {
    Copy-Item -Path (Join-Path $Root $pat) -Destination $Stage -Force -ErrorAction SilentlyContinue
}
# 5. Persistent state from logs (NOT the logs themselves - those stay local)
New-Item -ItemType Directory -Force -Path "$Stage\logs" | Out-Null
$stateFiles = @("brain_state.json", "dashboard_config.json", "brain_memory.json")
foreach ($f in $stateFiles) {
    $p = Join-Path $Root "logs\$f"
    if (Test-Path $p) { Copy-Item $p "$Stage\logs\" -Force }
}

# 6. Strip junk from staged copy
Get-ChildItem $Stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem $Stage -Recurse -File -Include "*.pyc" | Remove-Item -Force
# tv_alert_setup is a 574 MB local one-time setup tool - not needed on the VPS
if (Test-Path "$Stage\tools\tv_alert_setup") { Remove-Item -Recurse -Force "$Stage\tools\tv_alert_setup" }

# 7. Zip it
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path "$Stage\*" -DestinationPath $Zip -CompressionLevel Optimal
$mb = [math]::Round((Get-Item $Zip).Length / 1MB, 1)
Write-Host ""
Write-Host "[OK] Package ready: $Zip ($mb MB)"
Write-Host "     WARNING: contains config\.env (Telegram/API secrets). Transfer via RDP copy or private channel only."
