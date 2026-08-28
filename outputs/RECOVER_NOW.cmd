@echo off
REM ============================================================================
REM   RECOVER_NOW.cmd  —  Sumit's one-click laptop-restart recovery
REM
REM   Just double-click this file. It runs both fixes in sequence:
REM     1. fix_popups_2026-05-08.cmd   - silence terminal flashes
REM     2. fix_all_2026-05-08.cmd      - restart ngrok+brain+webhook pipeline
REM
REM   Total runtime: ~90 seconds. Leave the window open until "DONE" appears.
REM ============================================================================

REM Run from the script's own directory (outputs\)
cd /d "%~dp0"

echo.
echo ============================================================
echo   STEP 1 of 2  —  Silencing terminal popups
echo ============================================================
call fix_popups_2026-05-08.cmd

echo.
echo.
echo ============================================================
echo   STEP 2 of 2  —  Restarting trading pipeline (brain+webhook+ngrok)
echo ============================================================
call fix_all_2026-05-08.cmd

echo.
echo ============================================================
echo  ALL DONE.  Press any key to close this window.
echo ============================================================
pause >nul
