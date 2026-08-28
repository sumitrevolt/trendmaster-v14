@echo off
REM =====================================================================
REM 04_watch_signals_2026-05-09.cmd
REM
REM Tail tv_webhook.log + python_executor.log together so you can watch
REM the full pipeline in real time as Rocket Prime fires.
REM
REM Expected sequence on a successful BTCUSD signal:
REM
REM   tv_webhook.log:
REM     [INFO] INFERRED BUY for BTCUSD pos_in_range=0.31 last3_pct=-0.42 rsi=28 conf=0.85
REM     [INFO] TV->EA OK  symbol=BTCUSD dir=BUY tf=M15 conf=0.850 path=...trendmaster_signals_BTCUSD.json strategy=rocket_prime_inferred
REM
REM   python_executor.log (within ~5s):
REM     [INFO] heartbeat: ... placed=1 ...
REM     [INFO] ORDER PLACED BTCUSD BUY ...
REM
REM   Telegram phone: trade message arrives ~immediately after ORDER PLACED.
REM
REM Press Ctrl+C to stop tailing.
REM =====================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============================================================
echo   Watching pipeline -- Ctrl+C to stop
echo ============================================================

powershell -NoProfile -Command ^
  "$tw = Start-Job -ScriptBlock { Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\tv_webhook.log' -Tail 5 -Wait | ForEach-Object { '[WEBHOOK ] ' + $_ } }; ^
   $px = Start-Job -ScriptBlock { Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\python_executor.log' -Tail 1 -Wait | ForEach-Object { if ($_ -notmatch 'heartbeat: iter=') { '[EXEC    ] ' + $_ } } }; ^
   try { while ($true) { Receive-Job $tw; Receive-Job $px; Start-Sleep -Milliseconds 500 } } finally { Stop-Job $tw,$px; Remove-Job $tw,$px -Force }"
