$ErrorActionPreference = 'Continue'
$root = 'C:\Users\Ratanshila\Documents\autmated trading'
$py   = Join-Path $root '.venv\Scripts\python.exe'
$script = Join-Path $root 'tools\tv_alert_setup\run_instant_freq_atomic.py'
$logDir = Join-Path $root 'logs'
$outLog = Join-Path $logDir 'set_freq.out'
$errLog = Join-Path $logDir 'set_freq.err'
Set-Location $root
& $py $script *> $outLog
"EXIT $LASTEXITCODE" | Out-File -Append $outLog -Encoding utf8
