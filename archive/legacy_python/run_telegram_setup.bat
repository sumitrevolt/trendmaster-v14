@echo off
set PYTHON=C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe
set SCRIPT=C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\auto_telegram_setup.py
set LOG=C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_setup_log.txt
"%PYTHON%" "%SCRIPT%" > "%LOG%" 2>&1
type "%LOG%"
pause
