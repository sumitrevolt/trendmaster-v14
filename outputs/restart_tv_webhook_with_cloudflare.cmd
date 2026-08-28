@echo off
REM Switch the public tunnel from ngrok to Cloudflare Tunnel.
REM Assumes operator has run install_cloudflared.cmd and updated config/.env
REM with TUNNEL_MODE=cloudflare + CLOUDFLARE_TUNNEL_UUID + CLOUDFLARE_HOSTNAME.

cd /d "%~dp0\.."

echo Killing existing ngrok + tv_webhook processes...
taskkill /F /IM ngrok.exe 2>nul

echo.
echo Killing existing tv_webhook_receiver...
for /f "tokens=2 delims=," %%P in ('
    wmic process where "name='pythonw.exe' and commandline like '%%tv_webhook_receiver%%'" get processid /format:csv ^| findstr /r "[0-9]"
') do (
    taskkill /F /PID %%P 2>nul
)

echo.
echo Killing any existing cloudflared instances...
taskkill /F /IM cloudflared.exe 2>nul

timeout /t 3 /nobreak > nul

echo.
echo Starting tv_webhook_receiver (local listener)...
start "TrendMaster TV Webhook" /MIN cmd /c "title TV Webhook && cd /d %~dp0\.. && .venv\Scripts\pythonw.exe -m ai_trading_agents.tv_webhook_receiver 1>> logs\tv_webhook.log 2>&1"

timeout /t 3 /nobreak > nul

echo Starting Cloudflare Tunnel...
start "TrendMaster Cloudflare Tunnel" /MIN cmd /c "title Cloudflare Tunnel && cd /d %~dp0\.. && .venv\Scripts\python.exe tools\cloudflare_tunnel_runner.py 1>> logs\cloudflare_tunnel_runner.log 2>&1"

echo.
echo ============================================================
echo   Verifying...
echo ============================================================
timeout /t 8 /nobreak > nul

echo.
echo Local webhook health:
curl -s http://127.0.0.1:5005/health
echo.
echo.

set /p HOSTNAME="Enter your CLOUDFLARE_HOSTNAME (e.g. bot-tv.example.com) to verify public reach: "
if defined HOSTNAME (
    echo Public health via %HOSTNAME%:
    curl -s "https://%HOSTNAME%/health"
    echo.
)

echo.
echo If both health checks return ok, tunnel is live.
echo Update TV alerts to point to: https://%HOSTNAME%/tv-signal?secret=^<...^>
echo.
pause
