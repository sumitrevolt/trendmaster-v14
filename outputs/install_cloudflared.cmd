@echo off
REM One-shot Cloudflare Tunnel setup. Run ONCE.
REM
REM What it does:
REM   1. Install cloudflared via winget (silent)
REM   2. Open browser for Cloudflare account auth (~30 sec)
REM   3. Create named tunnel "trendmaster"
REM   4. Print the UUID + DNS-route command operator pastes back here
REM
REM After this, paste UUID + your routed hostname into config/.env:
REM   CLOUDFLARE_TUNNEL_UUID=<uuid printed below>
REM   CLOUDFLARE_HOSTNAME=bot-tv.your-cf-domain.com
REM
REM Then update config/.env: TUNNEL_MODE=cloudflare
REM Then restart webhook: tools\start_tv_webhook.cmd
REM Then update TV alerts to use new https://CLOUDFLARE_HOSTNAME/tv-signal?secret=...

echo.
echo ============================================================
echo   Cloudflare Tunnel — first-time install
echo ============================================================
echo.

REM Step 1 — install
where cloudflared >nul 2>&1
if errorlevel 1 (
    echo [1/4] Installing cloudflared via winget...
    winget install --id Cloudflare.cloudflared --silent --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo [X] winget install failed. Manually download from:
        echo     https://github.com/cloudflare/cloudflared/releases
        pause
        exit /b 1
    )
) else (
    echo [1/4] cloudflared already installed.
)

REM Refresh PATH for this session so cloudflared is found
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul ^| findstr /i PATH') do set "USER_PATH=%%B"
set "PATH=%PATH%;%USER_PATH%"

echo.
echo [2/4] Logging into Cloudflare (browser will open) — pick any free zone if asked
cloudflared tunnel login
if errorlevel 1 (
    echo [X] login failed
    pause
    exit /b 2
)

echo.
echo [3/4] Creating named tunnel 'trendmaster'...
cloudflared tunnel create trendmaster
if errorlevel 1 (
    echo [INFO] tunnel may already exist. Listing...
    cloudflared tunnel list
)

echo.
echo [4/4] Done. NEXT STEPS:
echo.
echo   A. Note the tunnel UUID printed above (32-char hex).
echo.
echo   B. Route DNS: pick a hostname under your CF zone, e.g. bot-tv.example.com
echo      Run:    cloudflared tunnel route dns trendmaster bot-tv.example.com
echo.
echo   C. Edit config\.env, set:
echo        TUNNEL_MODE=cloudflare
echo        CLOUDFLARE_TUNNEL_UUID=^<32-char hex from step A^>
echo        CLOUDFLARE_HOSTNAME=bot-tv.example.com
echo.
echo   D. Restart webhook: outputs\restart_tv_webhook_with_cloudflare.cmd
echo.
echo   E. Update each TV alert webhook URL to:
echo        https://bot-tv.example.com/tv-signal?secret=^<TV_WEBHOOK_SECRET^>^&symbol=BTCUSD^&tf=5
echo.
pause
