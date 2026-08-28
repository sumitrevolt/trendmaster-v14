@echo off
echo === Install webhook watchdog (every 5 min) ===
schtasks /Create ^
    /TN "TrendMaster Webhook Watchdog" ^
    /TR ".venv\\Scripts\\python.exe \"C:\\Users\\Ratanshila\\Documents\\autmated trading\\tools\\tv_webhook_watchdog.py\"" ^
    /SC MINUTE /MO 5 ^
    /F
echo.
echo === Verify ===
schtasks /Query /TN "TrendMaster Webhook Watchdog" /FO LIST
echo.
echo === Trigger one-shot now ===
schtasks /Run /TN "TrendMaster Webhook Watchdog"
ping 127.0.0.1 -n 6 >nul
echo.
echo === Tail watchdog log ===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\tv_webhook_watchdog.log' -Tail 15 -ErrorAction SilentlyContinue"
