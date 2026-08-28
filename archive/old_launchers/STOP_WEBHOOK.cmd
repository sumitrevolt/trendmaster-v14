@echo off
REM Stops the webhook receiver + Cloudflare tunnel started by start_webhook_full.cmd
echo Killing TV_Webhook processes...
for /f "tokens=2" %%a in ('tasklist /v /fi "imagename eq python.exe" ^| findstr /i "TV_Webhook"') do taskkill /F /PID %%a 2>nul
echo Killing cloudflared...
taskkill /F /IM cloudflared.exe 2>nul
echo Done.
pause
