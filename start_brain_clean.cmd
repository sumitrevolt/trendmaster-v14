@echo off

REM v14-godmode preflight 2026-04-25 — abort if brain source missing
REM [2026-08-25] C:\TrendMaster_aita_canonical junction was retired;
REM ai_trading_agents is now a real folder on D:. Check the live source.
if not exist "D:\autmated trading\ai_trading_agents\trend_master_brain.py" (
    echo [X] PRE-FLIGHT FAIL: D:\autmated trading\ai_trading_agents\ is empty or missing.
    echo     Restore the brain package from archive\legacy_python\.
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
REM 2026-05-06 — surgical brain-only kill (was: taskkill /F /IM python.exe).
REM [2026-08-25] also match pythonw.exe — the live brain runs under the
REM venv's windowless interpreter; python.exe-only filter silently killed
REM NOTHING and the "restart" left the old-config brain running.
echo === surgical kill of brain process(es) only ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | ForEach-Object { Write-Host '  killing brain PID' $_.ProcessId; taskkill /F /PID $_.ProcessId 2>$null }"
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

REM 2026-04-30 — crash detection. Earlier the brain could die during boot
REM with a Traceback in logs\trend_master_brain.err while this script kept
REM happily reporting success, leading to a watch-pet restart loop nobody
REM noticed for hours. If the .err file ends with a Traceback, refuse to
REM claim success so the operator (and any wrapping watch-pet) sees the
REM failure immediately. See docs/POSTMORTEMS/2026-04-30 (.resolve()
REM regression #3 — brain restart loop).
echo === checking for boot-time crash ===
.venv\Scripts\python.exe -c "import sys, pathlib; p = pathlib.Path(r'logs\trend_master_brain.err'); txt = p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''; sys.exit(2 if 'Traceback' in txt else 0)"
if errorlevel 2 (
    echo [X] BOOT CRASH: logs\trend_master_brain.err contains a Traceback.
    echo     Tail of error log:
    powershell -NoProfile -Command "Get-Content -Path 'logs\trend_master_brain.err' -Tail 25"
    echo     Brain is NOT running. Fix the import error before retrying.
    exit /b 5
)

REM 2026-04-29 — capture the brain PID so watch-pets / brain-liveness
REM can verify aliveness. Delegated to tools\write_brain_pid.py to avoid
REM cmd quoting hell. Reads brain.lock first (set by SingleInstanceLock),
REM falls back to scanning python.exe for trend_master_brain.
echo === writing logs\brain.pid ===
.venv\Scripts\python.exe tools\write_brain_pid.py

echo === DONE - check find_brain.cmd for status ===
