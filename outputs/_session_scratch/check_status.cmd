@echo off
echo === Python processes running tv_alert_setup or reset_and_create ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup|reset_and_create|setup_tv_alerts|delete_all_alerts' } | Select-Object ProcessId,@{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(180, $_.CommandLine.Length))}} | Format-List"
echo.
echo === Chromium browser windows ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -match 'tv_alert_setup' } | Select-Object ProcessId | Measure-Object | Select-Object @{N='ChromiumProcs';E={$_.Count}}"
echo.
echo === alerts_done.json content ===
type "C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup\alerts_done.json" 2>nul || echo (file does not exist yet)
echo.
echo === Last 20 lines tv_signals.jsonl ===
powershell -NoProfile -Command "Get-Content 'C:\Users\Ratanshila\Documents\autmated trading\logs\tv_signals.jsonl' -Tail 5 -ErrorAction SilentlyContinue"
