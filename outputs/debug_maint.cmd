@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Direct python run with stderr ===
.venv\Scripts\python.exe -u tools\daily_maintenance.py 2>&1
echo.
echo === Exit code: %ERRORLEVEL% ===
echo.
echo === backups dir? ===
if exist backups echo YES exists else echo NO does not
