@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Is OAuth helper running on port 8766? ===
netstat -ano 2>nul | findstr ":8766"
echo.
echo === Python OAuth process? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*ctrader_oauth*' } | Select-Object ProcessId, CreationDate | Format-Table"
echo.
echo === Direct authorize URL (click to open) ===
echo.
echo https://openapi.ctrader.com/apps/auth?client_id=27545_kMZOIvV5f1cDj5dlOjSWfEF1MbOLo6W5ylXPO9LgAQwSOF89Pt^&redirect_uri=http%%3A%%2F%%2F127.0.0.1%%3A8766%%2Fctrader-oauth%%2Fcallback^&scope=trading
echo.
