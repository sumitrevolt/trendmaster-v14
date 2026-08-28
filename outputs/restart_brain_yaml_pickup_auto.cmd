@echo off
cd /d "%~dp0\.."
"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\restart_brain_yaml_pickup.py" > "%~dp0\..\logs\restart_brain_yaml_pickup.log" 2>&1
type "%~dp0\..\logs\restart_brain_yaml_pickup.log"
echo.
timeout /t 30 /nobreak > nul
