@echo off
REM Start the TrendMaster v14 dashboard in a detached window on :8000.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Kill any stale dashboard listener first (optional — harmless if none).
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do (
    echo [i] Killing stale dashboard PID %%p
    taskkill /PID %%p /F /T >nul 2>&1
)

if not exist "logs" mkdir logs

echo [i] Launching dashboard on http://localhost:8000 ...
start "TrendMaster v14 Dashboard" cmd /k "title TrendMaster v14 Dashboard && python -u tools\dashboard.py > logs\dashboard.out 2> logs\dashboard.err"

echo [i] Waiting 5 seconds for the FastAPI server to boot ...
timeout /t 5 /nobreak >nul

echo.
echo [i] Dashboard spawn attempted. Probing /healthz ...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000/healthz' -TimeoutSec 5; Write-Host ('status=' + $r.StatusCode); Write-Host $r.Content } catch { Write-Host ('probe failed: ' + $_.Exception.Message) }"
echo.
