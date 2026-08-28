@echo off
REM ─────────────────────────────────────────────────────────────────────
REM  Resume cTrader OAuth flow (when ready)
REM
REM  PRE-CHECK: at https://openapi.ctrader.com/apps your app's redirect URI
REM  MUST be exactly:
REM      http://127.0.0.1:8766/ctrader-oauth/callback
REM  (no trailing slash, lowercase, port 8766 — NOT 8765)
REM
REM  If it's different there, either:
REM    (a) edit it in cTrader app settings to match the URI above, OR
REM    (b) edit tools\ctrader_oauth.py constant REDIRECT to match yours.
REM ─────────────────────────────────────────────────────────────────────

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Pre-flight: keys present? ===
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('config/.env'); import os; assert os.getenv('CTRADER_CLIENT_ID') and os.getenv('CTRADER_CLIENT_SECRET'), 'CTRADER_CLIENT_ID / CLIENT_SECRET missing'; print('  CLIENT_ID/SECRET present.')"
if errorlevel 1 (
    echo [X] Missing CTRADER_CLIENT_ID or CTRADER_CLIENT_SECRET in config\.env
    exit /b 1
)

echo.
echo === Killing any stale OAuth helper / port 8766 holders ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*ctrader_oauth*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"

echo.
echo === Launching OAuth helper (waits 5 min for click) ===
echo.
echo  >> Browser will open. cTrader login + click Authorize.
echo  >> Once redirect lands at 127.0.0.1:8766, tokens auto-save to config\.env
echo.
.venv\Scripts\python.exe tools\ctrader_oauth.py
if errorlevel 1 (
    echo.
    echo [X] OAuth failed. Possible causes:
    echo     1. Redirect URI mismatch  ^(see top of this file^)
    echo     2. Browser didn't open  -> copy the URL from logs\ctrader_oauth.out
    echo        and paste in browser manually
    echo     3. cTrader app not approved for trading scope  ^(check app status^)
    exit /b 2
)

echo.
echo === Discovering account_id ===
.venv\Scripts\python.exe tools\ctrader_executor.py --discover-accounts
echo.
echo === Once CTRADER_ACCOUNT_ID is set in .env, start the executor:
echo    start "" /B .venv\Scripts\pythonw.exe tools\ctrader_executor.py
echo.
echo  Watchdog will pick it up automatically on next 60s cycle.
