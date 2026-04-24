@echo off
title Sumit's Multi-Indicator Engine - XAUUSD M5
color 0A
chcp 65001 >nul 2>&1

echo.
echo  ============================================================
echo   SUMIT'S MULTI-INDICATOR SIGNAL ENGINE v1.0
echo   MACD + SuperBollingerTrend + ORB + Phoenix
echo   2 signals = NORMAL trade   3-4 signals = DOUBLE trade
echo  ============================================================
echo   Telegram : @Sumits_jarvis_bot
echo   Symbol   : XAUUSD  ^|  Timeframe : M5
echo   Lot      : 0.01 normal  /  0.02 double signal
echo  ============================================================
echo.
echo  Make sure MetaTrader5 is OPEN and LOGGED IN first!
echo  Press CTRL+C to stop.
echo.

set PY=C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe
set SC=C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\run_engine.py

"%PY%" "%SC%"

echo.
echo [STOPPED] Engine stopped.
pause
