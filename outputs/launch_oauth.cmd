@echo off
echo === Launch hidden OAuth helper via VBS ===
wscript.exe "C:\Users\Ratanshila\Documents\autmated trading\tools\ctrader_oauth_hidden.vbs"
ping 127.0.0.1 -n 4 >nul
echo.
echo === Verify port 8766 listening ===
netstat -ano | findstr ":8766"
echo.
echo === Verify python helper running ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*ctrader_oauth*' } | Select-Object ProcessId | Format-Table"
echo.
echo === Open browser to authorize URL ===
start "" "https://openapi.ctrader.com/apps/auth?client_id=27545_kMZOIvV5f1cDj5dlOjSWfEF1MbOLo6W5ylXPO9LgAQwSOF89Pt&redirect_uri=http%%3A%%2F%%2F127.0.0.1%%3A8766%%2Fctrader-oauth%%2Fcallback&scope=trading"
echo.
echo === Browser should now be open. Click 'Authorize'. ===
echo === Tokens will auto-save to config\.env when you click. ===
