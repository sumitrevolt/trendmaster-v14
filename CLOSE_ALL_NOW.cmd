@echo off
REM ===========================================================================
REM CLOSE ALL OPEN MT5 POSITIONS -- 2026-05-06
REM Sumit ko khud chalana hai (financial action).
REM Closes 10 open positions: 1 XNGUSD, 2 EURAUD, 1 EURUSD, 4 XAUUSD, 2 USDJPY
REM Realizes ~-$79.55 floating P/L into balance.
REM ===========================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo Confirming MT5 access...
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); print('login:', os.getenv('MT5_LOGIN'), 'server:', os.getenv('MT5_SERVER'))"
echo.
echo Press Ctrl+C in next 5 seconds to cancel...
ping 127.0.0.1 -n 6 >nul
echo.
.venv\Scripts\python.exe outputs\close_all_now.py
echo.
echo === Done. Press any key to close window ===
pause
