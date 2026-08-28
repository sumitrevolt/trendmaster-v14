@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo Opening cTrader auth page in browser...
start "" "https://openapi.ctrader.com/apps/auth?client_id=27545_kMZOIvV5f1cDj5dlOjSWfEF1MbOLo6W5ylXPO9LgAQwSOF89Pt&redirect_uri=http%%3A%%2F%%2F127.0.0.1%%3A8766%%2Fctrader-oauth%%2Fcallback&scope=trading"
echo.
echo Now starting OAuth helper to catch the redirect...
.venv\Scripts\python.exe tools\ctrader_oauth.py
