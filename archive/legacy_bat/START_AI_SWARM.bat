@echo off
title 🤖 AI SWARM TRADING BOT - STARTING...
color 0A
cls

echo.
echo  ██████████████████████████████████████████████
echo  █   AI SWARM TRADING BOT - AUTO LAUNCHER    █
echo  █   Oracle + StrategyBrain + ExecutionShield █
echo  ██████████████████████████████████████████████
echo.
echo  [1/3] Checking Python...
python --version
if %errorlevel% neq 0 (
    echo  ERROR: Python not found! Install Python 3.10+ first.
    pause
    exit /b 1
)

echo.
echo  [2/3] Installing dependencies...
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo  WARNING: Some packages may not have installed. Continuing...
)

echo.
echo  [3/3] Launching AI Swarm...
echo  Make sure MetaTrader 5 is OPEN and LOGGED IN!
echo.
echo  Press CTRL+C to stop the swarm.
echo  ============================================
echo.

:LOOP
python ai_swarm_main.py
echo.
echo  [!] Swarm stopped or crashed. Restarting in 10 seconds...
echo  [!] Press CTRL+C to exit.
timeout /t 10 /nobreak
goto LOOP
