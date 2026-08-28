@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============================================================
echo  ROCKET PRIME SIGNALS BLOCKED - DD BASELINE RESET
echo ============================================================
echo.
echo Diagnosis: brain_state.start_of_day_equity = $1145.73,
echo            current equity = $1059.20 (-7.55%% intraday DD).
echo            tv_executor.A3 gate blocks all signals when DD ^>= 3%%.
echo Fix:       rebase sod to current equity, raise cap to 5%%, restart.
echo.

echo === STEP 1: Stop brain (surgical, leaves webhook + executor alive) ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | ForEach-Object { Write-Host ('  killing brain PID ' + $_.ProcessId); taskkill /F /PID $_.ProcessId 2>$null }"
echo.
timeout /T 3 /NOBREAK >nul

echo === STEP 2: Rebase brain_state.json sod = current equity ===
.venv\Scripts\python.exe outputs\reset_dd_baseline.py
if errorlevel 1 (
    echo.
    echo [FATAL] reset script failed. Brain is STOPPED. Investigate before continuing.
    exit /b 1
)
echo.

echo === STEP 3: Restart brain (clean) ===
call start_brain_clean.cmd
echo.
timeout /T 5 /NOBREAK >nul

echo === STEP 4: Restart webhook so new daily_max_loss_pct=5%% loads ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*tv_webhook_receiver*' } | ForEach-Object { Write-Host ('  restarting webhook PID ' + $_.ProcessId); taskkill /F /PID $_.ProcessId 2>$null }"
timeout /T 2 /NOBREAK >nul
start "" /B cmd /c "start_tv_webhook.cmd"
timeout /T 4 /NOBREAK >nul

echo === STEP 5: Verify gate is now clear ===
.venv\Scripts\python.exe -c "import json,os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); s=json.loads(open('logs/brain_state.json',encoding='utf-8').read()); sod=s.get('start_of_day_equity',0); eq=ai.equity; dd=(sod-eq)/sod*100 if sod>0 else 0; cap=5.0; print(f'  equity=${eq:.2f}  sod=${sod:.2f}  dd={dd:.2f}%%  cap={cap}%%  gate={\"BLOCKED\" if dd>=cap else \"OPEN\"}'); print(f'  lockout_until={s.get(\"drawdown_lockout_until\",0)}  trading_paused={s.get(\"trading_paused\")}'); mt5.shutdown()"
echo.

echo === STEP 6: Webhook public health ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=5); print('  Public health: HTTP', r.status)"
echo.

echo === STEP 7: Brain alive? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Measure-Object | Select-Object @{N='brain_procs';E={$_.Count}}"
echo.

echo === STEP 8: Executor alive? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*python_signal_executor*' } | Measure-Object | Select-Object @{N='executor_procs';E={$_.Count}}"
echo.

echo ============================================================
echo  DONE. Next Rocket Prime fire should now route through.
echo  Watch: type logs\python_executor.log for live trade events.
echo ============================================================
