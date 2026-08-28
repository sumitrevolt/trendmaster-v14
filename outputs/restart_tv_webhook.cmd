@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\restart_tv_webhook_receiver.py" > "%~dp0\..\logs\restart_tv_webhook.log" 2>&1
type "%~dp0\..\logs\restart_tv_webhook.log"
echo.
timeout /t 30 /nobreak > nul
