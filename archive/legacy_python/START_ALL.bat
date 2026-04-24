@echo off
title Sumit's AI Trading System - FULL LAUNCH
color 0A
chcp 65001 >nul 2>&1

set PY=C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe
set PROJ=C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents

echo.
echo  ================================================================
echo   SUMIT'S AI TRADING SYSTEM - FULL LAUNCH
echo  ================================================================
echo   1. Jarvis Engine    : MACD + SBT + ORB + Phoenix (M5 signals)
echo   2. AI Agent Team    : 9 Agents - News, SMC, Institutional
echo   3. Telegram Bot     : @Sumits_jarvis_bot (all alerts here)
echo  ================================================================
echo.
echo  Make sure MetaTrader5 is OPEN and LOGGED IN!
echo.

:: Launch Jarvis Engine in new window
echo [1/2] Starting Jarvis Signal Engine...
start "Jarvis Signal Engine" cmd /k "chcp 65001 >nul && "%PY%" "%PROJ%\jarvis_engine.py""

timeout /t 3 /nobreak >nul

:: Launch AI Agent Team in new window
echo [2/2] Starting AI Agent Team...
start "AI Agent Team" cmd /k "chcp 65001 >nul && "%PY%" "%PROJ%\main.py""

echo.
echo  ================================================================
echo   BOTH SYSTEMS STARTED!
echo   - Jarvis Engine    : watching M5 bars
echo   - AI Agent Team    : dashboard at http://localhost:8000
echo   - Telegram alerts  : @Sumits_jarvis_bot
echo  ================================================================
echo.
pause
