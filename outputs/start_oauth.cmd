@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Starting cTrader OAuth flow ===
echo === Your browser will open. Click 'Authorize' on the cTrader page. ===
echo === Wait here ^- tokens get auto-saved to config\.env ===
echo.
.venv\Scripts\python.exe tools\ctrader_oauth.py
