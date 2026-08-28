# server_bootstrap.ps1 - one-shot setup on a FRESH Windows VPS
# 1. Copy trendmaster_stack.zip to the VPS (RDP clipboard / drive redirect).
# 2. Install MetaTrader 5 from Octa and log into the account ONCE via RDP.
# 3. Then run this from an elevated PowerShell inside the extracted folder:
#    powershell -NoProfile -ExecutionPolicy Bypass -File server_bootstrap.ps1
$ErrorActionPreference = "Stop"
$Root = (Get-Location).Path
Write-Host "=== TrendMaster VPS bootstrap in: $Root ==="

# --- 0. Must run from the extracted stack folder -----------------------------
if (-not (Test-Path "$Root\ai_trading_agents\trend_master_brain.py")) {
    Write-Host "[X] trend_master_brain.py not found here. cd into the extracted folder first." -ForegroundColor Red
    exit 1
}

# --- 1. Python 3.11 ----------------------------------------------------------
$py = Get-Command py -ErrorAction SilentlyContinue
$have311 = $false
if ($py) { $have311 = (& py -0p 2>$null) -match "3\.11" }
if (-not $have311) {
    Write-Host "=== Installing Python 3.11 via winget ==="
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    refreshenv 2>$null
}
# --- 2. venv + deps ----------------------------------------------------------
Write-Host "=== Creating .venv and installing requirements ==="
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# --- 3. MT5 data folder: install the EA --------------------------------------
Write-Host "=== Installing EA into MT5 data folder ==="
$dataDir = Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "MQL5") } | Select-Object -First 1
if ($dataDir -and (Test-Path "$Root\AI_SUPERBB_v14_TrendMaster.mq5")) {
    $experts = Join-Path $dataDir.FullName "MQL5\Experts"
    New-Item -ItemType Directory -Force -Path $experts | Out-Null
    Copy-Item "$Root\AI_SUPERBB_v14_TrendMaster.mq5" $experts -Force
    Write-Host "[OK] EA copied to $experts  (open MT5 -> Navigator -> compile in MetaEditor)"
} else {
    Write-Host "[!] MT5 data folder or EA not found - install MT5 + EA manually." -ForegroundColor Yellow
}

# --- 4. Start the stack ------------------------------------------------------
Write-Host "=== Starting brain (pre-flight + clean restart) ==="
cmd /c start_brain_clean.cmd
Write-Host "=== Starting dashboard (hidden, :8765) ==="
wscript.exe tools\hidden_dashboard.vbs
Write-Host "=== Starting signal executor (hidden) ==="
wscript.exe tools\hidden_python_executor.vbs
Write-Host "=== Starting webhook receiver + ngrok tunnel (hidden) ==="
# NOTE: ngrok authtoken is machine-local (%LOCALAPPDATA%\ngrok\ngrok.yml).
# Run once on the VPS:  ngrok config add-authtoken <token>
# and edit start_pipeline_hidden.cmd's ngrok path for this machine if needed.
cmd /c start_pipeline_hidden.cmd

# --- 5. Health verification --------------------------------------------------
Write-Host "=== Verifying (15s wait) ==="
Start-Sleep -Seconds 15
try {
    $h = Invoke-WebRequest -UseBasicParsing http://localhost:8765/ -TimeoutSec 5
    Write-Host "[OK] dashboard HTTP $($h.StatusCode) on :8765"
} catch { Write-Host "[!] dashboard not answering yet - check logs\dashboard_wrapper.log" -ForegroundColor Yellow }
$pidFile = "$Root\logs\brain.pid"
if (Test-Path $pidFile) {
    $bp = (Get-Content $pidFile).Trim()
    Write-Host "[OK] brain.pid = $bp"
} else { Write-Host "[!] brain.pid missing - check logs\trend_master_brain.err" -ForegroundColor Yellow }
Write-Host ""
Write-Host "=== Bootstrap DONE. Now in MT5: attach AI_SUPERBB_v14_TrendMaster EA to charts + enable AlgoTrading ==="
