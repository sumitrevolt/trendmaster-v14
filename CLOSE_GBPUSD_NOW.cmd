@echo off
REM ===========================================================================
REM CLOSE 2 unintended GBPUSD SELL positions (opened by Claude's test signal)
REM USDJPY BUY positions are KEPT (those are real Rocket Prime trades)
REM ===========================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo Confirming MT5 access...
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); print('login:', os.getenv('MT5_LOGIN'))"
echo.
echo Press Ctrl+C in next 3 sec to cancel...
ping 127.0.0.1 -n 4 >nul
.venv\Scripts\python.exe outputs\close_gbpusd_only.py
echo.
pause
