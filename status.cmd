@echo off
REM Shows current state of the TV-bot (processes, URL, recent signals).

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

powershell -NoProfile -Command ^
  "Write-Host '============================================================'; ^
   Write-Host '  TrendMaster TV-bot — status'; ^
   Write-Host '============================================================'; ^
   Write-Host ''; ^
   $rcv = Get-NetTCPConnection -LocalPort 5005 -State Listen -ErrorAction SilentlyContinue; ^
   if ($rcv) { Write-Host \"  Receiver:    LIVE on 127.0.0.1:5005 (pid $($rcv.OwningProcess))\" -ForegroundColor Green } ^
   else      { Write-Host '  Receiver:    DEAD (run start_bot.cmd)' -ForegroundColor Red }; ^
   $cf = Get-Process cloudflared -ErrorAction SilentlyContinue; ^
   if ($cf)  { Write-Host \"  Cloudflared: LIVE (pid $($cf.Id), since $($cf.StartTime.ToString('HH:mm:ss')))\" -ForegroundColor Green } ^
   else      { Write-Host '  Cloudflared: DEAD (run start_bot.cmd)' -ForegroundColor Red }; ^
   Write-Host ''; ^
   if (Test-Path 'logs\webhook_url.txt') { ^
     $url = (Get-Content 'logs\webhook_url.txt' -Raw).Trim(); ^
     Write-Host '  Webhook URL (paste into TV alert):'; ^
     Write-Host \"    $url\" -ForegroundColor Cyan; ^
   } else { Write-Host '  Webhook URL: (none — start_bot.cmd not run)' }; ^
   Write-Host ''; ^
   try { ^
     $s = Invoke-RestMethod -Uri 'http://127.0.0.1:5005/status' -TimeoutSec 3 -ErrorAction Stop; ^
     Write-Host '  Runtime metrics:'; ^
     Write-Host \"    uptime           $($s.uptime_s) s\"; ^
     Write-Host \"    requests total   $($s.metrics.requests_total)\"; ^
     Write-Host \"    writes ok        $($s.metrics.writes_ok)\"; ^
     Write-Host \"    duplicates       $($s.metrics.duplicates)\"; ^
     Write-Host \"    rejected         $($s.metrics.rejected)\"; ^
     Write-Host \"    auth fails       $($s.metrics.auth_fails)\"; ^
     Write-Host \"    dedup window     $($s.dedup_window_s) s\"; ^
   } catch { Write-Host '  (metrics unavailable — receiver not responding)' }; ^
   Write-Host ''; ^
   Write-Host '  Last 5 signals (from logs\tv_signals.jsonl):'; ^
   if (Test-Path 'logs\tv_signals.jsonl') { ^
     Get-Content 'logs\tv_signals.jsonl' -Tail 5 | ForEach-Object { ^
       $j = $_ | ConvertFrom-Json; ^
       $t = (Get-Date 0 -UFormat %%s) - $j.ts; ^
       Write-Host (\"    {0,-10} {1,-8} {2,-8} {3,-25} {4}s ago\" -f $j.event,$j.symbol,$j.direction,($j.tv_strategy ?? '-'), [int]$t); ^
     } ^
   } else { Write-Host '    (no signals yet)' }; ^
   Write-Host ''; ^
   Write-Host '============================================================';"

pause
