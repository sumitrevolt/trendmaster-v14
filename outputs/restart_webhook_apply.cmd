@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Restart webhook to apply patch ===
call start_tv_webhook.cmd
echo.
echo === Verify webhook up + new code loaded ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  HTTP', r.status, r.read().decode()[:120])"
echo.
echo === Verify patch is in place ===
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_webhook_receiver.py' -Pattern 'rocket_prime_url_direction|REJECT.*no direction in URL' | Select-Object -Last 5 | ForEach-Object { '  ' + $_.Line }"
