@echo off
echo === Investigate disabled tasks first ===
echo.
echo --- TrendMaster Junction Guard ---
schtasks /Query /TN "TrendMaster Junction Guard" /XML 2>nul | findstr /i "command arguments" | findstr /v "^$"
echo.
echo --- TrendMaster Brain Liveness ---
schtasks /Query /TN "TrendMaster Brain Liveness" /XML 2>nul | findstr /i "command arguments" | findstr /v "^$"
echo.
echo --- TrendMaster Watch-Pets ---
schtasks /Query /TN "TrendMaster Watch-Pets" /XML 2>nul | findstr /i "command arguments" | findstr /v "^$"
echo.
echo === Delete my duplicate Webhook Watchdog ===
schtasks /Delete /TN "TrendMaster Webhook Watchdog" /F
echo.
echo === Enable Junction Guard (junction breaks have hit 4x) ===
schtasks /Change /TN "TrendMaster Junction Guard" /ENABLE 2>nul
echo.
echo === Enable Schtasks Audit (drift detection) ===
schtasks /Change /TN "TrendMaster Schtasks Audit" /ENABLE 2>nul
echo.
echo === Final task list ===
schtasks /Query /FO TABLE | findstr /i "TrendMaster"
