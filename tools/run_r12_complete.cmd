@echo off
REM =============================================================================
REM run_r12_complete.cmd - one-shot orchestrator for R12 ship sequence.
REM
REM Runs (in order, fail-fast):
REM   1) tools\commit_r12_fixes.cmd        -- bundles 4 file changes
REM   2) start_brain_clean.cmd             -- restarts brain (detached)
REM   3) wait 30s for brain to bootstrap
REM   4) tools\diagnose_zero_trades.py     -- prints MIN_CONF + clearing count
REM   5) pause                             -- keeps window open for review
REM
REM Driven by Claude/computer-use; `pause` at end is INTENTIONAL so the
REM diagnose output stays on screen for screenshot verification.
REM =============================================================================

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo.
echo ==========================================================================
echo   STEP 1/3 -- commit R12 fixes
echo ==========================================================================
call tools\commit_r12_fixes.cmd
if errorlevel 1 (
    echo [X] commit_r12_fixes.cmd failed - halting orchestrator
    pause
    exit /b 1
)

echo.
echo ==========================================================================
echo   STEP 2/3 -- restart brain (clean)
echo ==========================================================================
call start_brain_clean.cmd
if errorlevel 1 (
    echo [X] start_brain_clean.cmd failed - halting orchestrator
    pause
    exit /b 2
)

echo.
echo ==========================================================================
echo   wait 30s for brain to settle past first tick
echo ==========================================================================
ping 127.0.0.1 -n 31 >nul

echo.
echo ==========================================================================
echo   STEP 3/3 -- diagnose
echo ==========================================================================
.venv\Scripts\python.exe tools\diagnose_zero_trades.py
echo.
echo ==========================================================================
echo   ORCHESTRATOR DONE -- review output above
echo ==========================================================================
echo Expected:
echo   MIN_CONF = 0.58
echo   Verdict  = OK
echo   Clearing = 10/18 or more (was 7/18 at MIN_CONF=0.70)
echo.
pause
