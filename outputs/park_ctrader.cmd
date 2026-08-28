@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Kill dangling OAuth helper (port 8766) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*ctrader_oauth*' } | ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null; Write-Host ('  killed ' + $_.ProcessId) }"
echo.
echo === Verify port 8766 freed ===
netstat -ano 2>nul | findstr ":8766" || echo   (port free)
echo.

echo ============== FINAL OCTAFX-SIDE HEALTH ==============
echo.
echo --- Brain alive? ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Measure-Object | Select-Object @{N='brain_procs';E={$_.Count}}"
echo.

echo --- Webhook + ngrok? ---
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  Public health: HTTP', r.status)"
powershell -NoProfile -Command "$ng=(Get-CimInstance Win32_Process -Filter \"name='ngrok.exe'\").Count; Write-Host ('  ngrok procs: ' + $ng)"
echo.

echo --- Executor (OctaFX MT5) ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Measure-Object | Select-Object @{N='executor_procs';E={$_.Count}}"
echo.

echo --- Dashboard ---
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('http://localhost:8765', timeout=3); print('  Dashboard:', r.status)"
echo.

echo --- TV alerts state ---
.venv\Scripts\python.exe outputs\verify_alerts_simple.py
echo.

echo --- Account state ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  positions={len(pos)}'); mt5.shutdown()"
echo.

echo --- Active scheduled tasks ---
schtasks /Query /FO TABLE 2>nul | findstr /i "TrendMaster" | findstr /v "Disabled" | find /c /v ""
echo.

echo --- Plot direction routing live? ---
powershell -NoProfile -Command "if (Test-Path 'logs\tv_plot_values.jsonl') { $lines=(Get-Content 'logs\tv_plot_values.jsonl').Count; Write-Host ('  tv_plot_values.jsonl: ' + $lines + ' entries logged') }"
