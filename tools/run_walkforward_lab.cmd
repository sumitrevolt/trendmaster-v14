@echo off
REM Wrapper invoked by Claude scheduled task / Windows schtasks.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM 2026-04-30: heal the ai_trading_agents junction before invoking python.
REM Without this, pre-commit can leave the junction broken between scheduled
REM runs and ea_parity phase fails with "No module named ai_trading_agents.multi_agent".
REM Mirrors start_brain_clean.cmd preflight. Postmortem:
REM   docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md
call tools\restore_junction.cmd >> logs\walkforward_lab.log 2>&1

.venv\Scripts\python.exe tools\walkforward_lab.py --symbol all >> logs\walkforward_lab.log 2>&1
