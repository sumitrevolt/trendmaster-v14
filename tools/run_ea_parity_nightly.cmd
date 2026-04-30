@echo off
REM Wrapper invoked by Windows Task Scheduler. Exists so schtasks /tr
REM can point at a single path instead of juggling cmd-quoting hell.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM 2026-04-30: heal the ai_trading_agents junction before invoking python.
REM Same pre-flight as run_walkforward_lab.cmd; see that file for rationale.
call tools\restore_junction.cmd >> logs\ea_parity_nightly.log 2>&1

.venv\Scripts\python.exe tools\ea_parity_nightly.py >> logs\ea_parity_nightly.log 2>&1
