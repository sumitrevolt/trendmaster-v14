@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === 1. Brain process check ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
echo.
echo === 2. Webhook process check ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table -AutoSize"
echo.
echo === 3. Webhook health ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  HTTP', r.status, r.read().decode()[:100])" 2>&1 | findstr /v Traceback
echo.
echo === 4. Last 30 lines brain log ===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\trend_master_brain.out' -Tail 30 -ErrorAction SilentlyContinue"
echo.
echo === 5. Diagnose ===
.venv\Scripts\python.exe tools\diagnose_zero_trades.py
