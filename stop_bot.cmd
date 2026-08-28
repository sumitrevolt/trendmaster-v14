@echo off
REM Stops the webhook receiver and Cloudflare tunnel cleanly.

echo Stopping TrendMaster TV-bot...

powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Write-Host '[+] receiver and tunnel stopped'"

echo.
echo Bot stopped. Run start_bot.cmd to relaunch.
echo.
pause
