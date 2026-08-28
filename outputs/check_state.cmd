@echo off
cd /d "%~dp0\.."
echo === Webhook /health check ===
curl -s -m 4 http://127.0.0.1:5005/health
echo.
echo === Recent webhook log (last 5) ===
powershell -NoProfile -Command "Get-Content 'logs\tv_webhook.log' -Tail 5"
echo.
echo === Recent executor log (last 5) ===
powershell -NoProfile -Command "Get-Content 'logs\python_executor.log' -Tail 5"
echo.
echo === Python processes ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Select-Object ProcessId, Name, @{N='Cmd';E={$_.CommandLine.Substring(0, [Math]::Min(120, $_.CommandLine.Length))}} | Format-Table -AutoSize"
echo.
echo Done.
timeout /t 8 /nobreak > nul
