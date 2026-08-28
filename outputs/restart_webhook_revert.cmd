@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Restart webhook with inference re-enabled (back to "pehle jaise") ===
call start_tv_webhook.cmd
echo.
echo === Health check ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  HTTP', r.status, r.read().decode()[:120])"
echo.
echo === Verify both URL-direction priority AND inference fallback are present ===
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_webhook_receiver.py' -Pattern 'rocket_prime_url_direction|rocket_prime_inferred' | Select-Object -Last 4 | ForEach-Object { '  ' + $_.Line }"
