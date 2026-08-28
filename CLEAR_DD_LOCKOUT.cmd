@echo off
REM ===========================================================================
REM CLEAR STALE DD LOCKOUT (2026-05-06)
REM Stale drawdown_lockout_until=1778112000 in brain_state.json is blocking EA.
REM Account is currently +$8 vs SoD — no real DD. Lockout is leftover from
REM morning sweep. This script backs up state, then clears lockout + cooldown
REM so EA resumes trading on next Rocket Prime signal.
REM ===========================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe outputs\clear_dd_lockout.py
echo.
echo === Done. Press any key to close ===
pause
