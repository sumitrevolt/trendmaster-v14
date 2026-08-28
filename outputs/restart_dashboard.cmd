@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Kill all dashboard processes ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*dashboard_server*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*dashboard_server*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"
ping 127.0.0.1 -n 4 >nul
echo.
echo === Verify zero ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*dashboard_server*' } | Measure-Object | Select-Object @{N='Remaining';E={$_.Count}}"
echo.
echo === Verify dashboard.lock cleared ===
del /f /q logs\dashboard_server.lock 2>nul
echo.
echo === Spawn fresh dashboard ===
start "" /MIN cmd /c ".venv\Scripts\pythonw.exe tools\dashboard_server.py"
ping 127.0.0.1 -n 6 >nul
echo.
echo === Confirm dashboard alive on port 8765 ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('http://localhost:8765', timeout=5); print('  HTTP', r.status)"
echo.
echo === Sample API endpoint test (non-trade-affecting) ===
.venv\Scripts\python.exe -c "import urllib.request as u, json; req=u.Request('http://localhost:8765/api/test-telegram', method='POST'); r=u.urlopen(req, timeout=8); d=json.loads(r.read().decode()); print('  /api/test-telegram:', d)"
echo.
echo === Verify dashAction function present in served HTML ===
.venv\Scripts\python.exe -c "import urllib.request as u; html=u.urlopen('http://localhost:8765', timeout=5).read().decode(); cnt=html.count('dashAction'); print('  dashAction occurrences:', cnt, '(should be 7+)')"
