@echo off
cd /d "C:\Users\ratanshila\Documents\autmated trading\ai_trading_agents"
"C:\Users\ratanshila\AppData\Local\Programs\Python\Python311\python.exe" -u ml_backtest_trainer.py > "C:\Users\ratanshila\Documents\train_log.txt" 2>&1
echo EXITCODE=%ERRORLEVEL%
