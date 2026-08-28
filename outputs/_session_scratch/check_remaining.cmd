@echo off
echo === Live python procs (tv_alert_setup) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup|reset_and_create|setup_tv_alerts|delete_all_alerts|inspect_alerts' } | Select-Object ProcessId, @{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(140, $_.CommandLine.Length))}} | Format-List"
echo.
echo === Playwright Chromium procs ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup|_browser_profile|ms-playwright' } | Measure-Object | Select-Object @{N='Count';E={$_.Count}}"
