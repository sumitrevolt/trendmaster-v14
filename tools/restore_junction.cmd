@echo off
REM =======================================================================
REM  tools\restore_junction.cmd
REM
REM  Restore the ai_trading_agents/ NTFS junction if it has been replaced
REM  with a real folder, removed, or never created.
REM
REM  Why this exists: pre-commit's git stash/restore cycle can replace
REM  the junction with a real (often empty) directory when it reformats
REM  files inside ai_trading_agents/. Other Windows tools that walk the
REM  worktree (OneDrive, antivirus, EDR) have done the same thing.
REM  See docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md.
REM
REM  Behavior:
REM    1. Verifies C:\TrendMaster_aita_canonical\ exists. If not, refuses
REM       to run (a missing target would create an empty junction and
REM       the brain would die at next import).
REM    2. If ai_trading_agents/ is already a junction with the right
REM       target, prints OK and exits 0.
REM    3. Otherwise, removes whatever is at ai_trading_agents/ and
REM       re-creates the junction.
REM    4. Verifies success with `dir /A:L` (lists reparse points only).
REM
REM  Exit codes:
REM    0  - junction healthy (already, or restored successfully)
REM    2  - canonical folder missing; cannot proceed
REM    3  - mklink failed
REM    4  - post-restore verification failed
REM =======================================================================
setlocal enableextensions

set "PROJECT_ROOT=C:\Users\Ratanshila\Documents\autmated trading"
set "JUNCTION=%PROJECT_ROOT%\ai_trading_agents"
set "CANONICAL=C:\TrendMaster_aita_canonical"

echo [restore_junction] checking canonical source at %CANONICAL%
if not exist "%CANONICAL%\trend_master_brain.py" (
    echo [restore_junction] FATAL: %CANONICAL%\trend_master_brain.py is missing.
    echo [restore_junction] Refusing to create an empty junction. Restore the canonical
    echo [restore_junction] folder first - see CLAUDE.md "Brain package maintenance" section
    echo [restore_junction] for the disaster-recovery copy command from archive\legacy_python\.
    exit /b 2
)

echo [restore_junction] checking junction at %JUNCTION%

REM `dir /A:L` lists reparse points (junctions / symlinks) only. If the
REM directory exists but is NOT a reparse point, this finds nothing and
REM we know to rebuild.
dir /A:L "%PROJECT_ROOT%" 2>nul | findstr /I /C:"ai_trading_agents" >nul
if %errorlevel% equ 0 (
    REM It IS a reparse point. Trust it; we don't try to introspect the
    REM target string from cmd (fsutil reparsepoint query needs admin).
    echo [restore_junction] OK: ai_trading_agents is a junction.
    exit /b 0
)

echo [restore_junction] junction missing or replaced with a real folder. Rebuilding.

if exist "%JUNCTION%" (
    echo [restore_junction] removing existing path: %JUNCTION%
    rd /s /q "%JUNCTION%"
    if exist "%JUNCTION%" (
        echo [restore_junction] FATAL: could not remove %JUNCTION%. Is something locking it?
        exit /b 3
    )
)

echo [restore_junction] creating junction: %JUNCTION% -^> %CANONICAL%
mklink /J "%JUNCTION%" "%CANONICAL%" >nul
if errorlevel 1 (
    echo [restore_junction] FATAL: mklink failed.
    exit /b 3
)

REM Re-verify.
dir /A:L "%PROJECT_ROOT%" 2>nul | findstr /I /C:"ai_trading_agents" >nul
if errorlevel 1 (
    echo [restore_junction] FATAL: post-restore verification failed.
    echo [restore_junction] %JUNCTION% does not appear as a reparse point.
    exit /b 4
)

echo [restore_junction] OK: junction restored. Verify with: dir /A:L "%PROJECT_ROOT%"
exit /b 0
