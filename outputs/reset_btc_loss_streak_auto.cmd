@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\reset_btc_loss_streak_2026-05-09.py" > "%~dp0\..\logs\reset_btc_loss_streak.log" 2>&1
type "%~dp0\..\logs\reset_btc_loss_streak.log"
echo.
timeout /t 30 /nobreak > nul
