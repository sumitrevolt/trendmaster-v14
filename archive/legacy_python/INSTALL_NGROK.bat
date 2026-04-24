@echo off
title Install ngrok
color 0B
cls

echo ============================================================
echo   ngrok Setup (needed for TradingView webhook)
echo ============================================================
echo.
echo ngrok = FREE tool jo tumhare PC ko public URL deta hai
echo TradingView usi URL pe signal bhejega
echo.

echo Checking if ngrok is installed...
ngrok version 2>nul
if %errorlevel% == 0 (
    echo ngrok already installed!
    goto :run
)

echo.
echo ngrok not found. Installing via winget...
winget install ngrok.ngrok

if %errorlevel% neq 0 (
    echo.
    echo Winget failed. Manual install karo:
    echo 1. https://ngrok.com/download pe jao
    echo 2. Download karo Windows version
    echo 3. Extract karo aur PATH mein daalo
    echo    OR isi folder mein rakho
    pause
    exit
)

:run
echo.
echo ============================================================
echo   ngrok is ready!
echo ============================================================
echo.
echo   Ab webhook bot chalu karo:
echo   1. START_WEBHOOK_BOT.bat run karo
echo   2. Phir NEW window mein ye command:
echo.
echo      ngrok http 5000
echo.
echo   3. Terminal mein aisa URL dikhega:
echo      https://abc123.ngrok-free.app
echo.
echo   4. TradingView alert mein:
echo      https://abc123.ngrok-free.app/webhook
echo ============================================================
echo.
pause
