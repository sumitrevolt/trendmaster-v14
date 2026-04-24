@echo off
title TradingView to MT5 Webhook Bot
color 0A
cls

echo ============================================================
echo   TradingView to MT5 Webhook Bot v1.0
echo ============================================================
echo.

echo [1/3] Installing required packages...
pip install flask MetaTrader5 requests --quiet
echo Done.
echo.

echo [2/3] Starting webhook server...
echo.
echo   Make sure MT5 is OPEN and LOGGED IN before continuing!
echo.
pause

echo [3/3] Starting server on port 5000...
echo.
echo   After server starts:
echo   1. Open NEW window and run: ngrok http 5000
echo   2. Copy the https URL from ngrok
echo   3. Paste in TradingView alert webhook field
echo   4. Add /webhook at the end
echo.
echo ============================================================
echo.

cd /d "%~dp0"
python tv_webhook_server.py

pause
