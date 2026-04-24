@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
copy /Y ai_trading_agents\trend_master_model.lgb ai_trading_agents\trend_master_model.lgb.bak >nul 2>&1
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe tools\train_v14_better.py > outputs\retrain_run.log 2>&1
echo DONE exit=%ERRORLEVEL%
