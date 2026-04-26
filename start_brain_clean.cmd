@echo off

REM v14-godmode preflight 2026-04-25 — abort if junction or canonical source missing
if not exist "C:\TrendMaster_aita_canonical\trend_master_brain.py" (
    echo [X] PRE-FLIGHT FAIL: C:\TrendMaster_aita_canonical\ is empty or missing.
    echo     The brain package junction target is gone. Restore from archive\legacy_python\.
    exit /b 2
)

REM 2026-04-26 — self-heal the junction if pre-commit (or any other
REM Windows tool that walks the worktree) replaced it with a real folder
REM or removed it. See docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md.
call tools\restore_junction.cmd
if errorlevel 1 (
    echo [X] PRE-FLIGHT FAIL: restore_junction.cmd reported an error.
    echo     Manual recovery required - see CLAUDE.md "Brain package maintenance".
    exit /b 4
)

.venv\Scripts\python.exe -c "import ai_trading_agents.trend_master_brain" >nul 2>&1
if errorlevel 1 (
    echo [X] PRE-FLIGHT FAIL: ai_trading_agents.trend_master_brain failed to import.
    echo     Check the junction: dir ai_trading_agents
    echo     Then verify: .venv\Scripts\python.exe -c "import ai_trading_agents.trend_master_brain"
    exit /b 3
)
echo [OK] PRE-FLIGHT: brain imports cleanly.

cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === killing any python.exe ===
taskkill /F /IM python.exe 2>nul
ping 127.0.0.1 -n 3 >nul

echo === clearing lock + truncating logs ===
del /f /q logs\brain.lock 2>nul
type nul > logs\trend_master_brain.out
type nul > logs\trend_master_brain.err

echo === nuking pycache ===
rmdir /s /q ai_trading_agents\__pycache__ 2>nul
rmdir /s /q config\__pycache__ 2>nul
rmdir /s /q tools\__pycache__ 2>nul

echo === starting brain detached ===
start "TrendMaster Brain - LIVE" /MIN cmd /c "title TrendMaster Brain - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py 1>> logs\trend_master_brain.out 2>> logs\trend_master_brain.err"

echo === wait 15s for boot ===
ping 127.0.0.1 -n 16 >nul

echo === DONE - check find_brain.cmd for status ===
