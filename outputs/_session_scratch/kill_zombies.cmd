@echo off
echo === Killing zombie Playwright python + Chromium ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup|reset_and_create|setup_tv_alerts|delete_all_alerts|inspect_alerts' } | ForEach-Object { taskkill /F /PID $_.ProcessId }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -match '_browser_profile|tv_alert_setup' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"
echo.
echo === Verify ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup' } | Measure-Object | Select-Object @{N='RemainingPyTV';E={$_.Count}}"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -match '_browser_profile' } | Measure-Object | Select-Object @{N='RemainingChromium';E={$_.Count}}"
