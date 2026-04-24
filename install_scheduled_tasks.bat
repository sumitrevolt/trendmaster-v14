@echo off
REM ============================================================
REM  Install Windows Scheduled Tasks for TrendMaster v14:
REM    1. Weekly news-feed refresh  (Monday 02:00 UTC)
REM    2. Daily digest + log rotation (01:00 UTC)
REM
REM  Run once as administrator (right-click -> Run as admin).
REM  To uninstall:  schtasks /delete /tn "TrendMaster <task>" /f
REM ============================================================
setlocal

set ROOT=%~dp0
set PY=python

echo.
echo Installing scheduled tasks...
echo ROOT=%ROOT%
echo.

REM --- Weekly news refresh ---
schtasks /create /f /sc weekly /d MON /st 02:00 ^
    /tn "TrendMaster Weekly News Refresh" ^
    /tr "cmd /c cd /d \"%ROOT%\" && %PY% -m ai_trading_agents.news_feed >> logs\news_feed.log 2>&1"
if errorlevel 1 ( echo [X] news-feed task failed ) else ( echo [OK] news-feed task registered )

REM --- Daily digest + rotation + backup ---
schtasks /create /f /sc daily /st 01:00 ^
    /tn "TrendMaster Daily Maintenance" ^
    /tr "cmd /c cd /d \"%ROOT%\" && %PY% main.py rotate >> logs\maintenance.log 2>&1 && %PY% main.py daily-report --telegram >> logs\maintenance.log 2>&1"
if errorlevel 1 ( echo [X] daily-maintenance task failed ) else ( echo [OK] daily-maintenance task registered )

echo.
echo == Current TrendMaster tasks ==
schtasks /query /fo LIST /tn "TrendMaster Weekly News Refresh"  2>nul | findstr /i "TaskName Next"
schtasks /query /fo LIST /tn "TrendMaster Daily Maintenance"     2>nul | findstr /i "TaskName Next"

echo.
echo Done. Tasks will run on their schedule. To run now:
echo   schtasks /run /tn "TrendMaster Daily Maintenance"
endlocal
