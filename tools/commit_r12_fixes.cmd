@echo off
REM =============================================================================
REM commit_r12_fixes.cmd — atomic commit of 2026-04-30 R12 follow-up fixes.
REM
REM Bundles 4 changes into ONE commit:
REM   1. config/trading_config.yaml         (untracked -> tracked, R12 0.70->0.58)
REM   2. tools/optimize_per_pair.py          (OOM fix: gc.collect + drop all_results)
REM   3. tools/run_walkforward_lab.cmd       (junction restore preflight)
REM   4. tools/run_ea_parity_nightly.cmd     (junction restore preflight, bonus)
REM
REM Run from project root:
REM   tools\commit_r12_fixes.cmd
REM =============================================================================

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Clear any stale git index.lock from a crashed prior session.
if exist ".git\index.lock" (
    echo [info] removing stale .git\index.lock
    del /f /q ".git\index.lock"
)

REM Heal junction first (pre-commit hooks may touch ai_trading_agents).
call tools\restore_junction.cmd
if errorlevel 1 (
    echo [X] junction restore failed - aborting commit
    exit /b 2
)

REM Stage exactly the 4 files we want; nothing else.
git add config\trading_config.yaml ^
        tools\optimize_per_pair.py ^
        tools\run_walkforward_lab.cmd ^
        tools\run_ea_parity_nightly.cmd
if errorlevel 1 exit /b 3

echo === staged ===
git diff --cached --stat
echo.

REM Commit. Pre-commit will run; if it reformats files, re-stage and retry once.
git commit -m "ops: R12 follow-up fixes - per-pair OOM, schtasks junction guard, yaml under git" ^
           -m "1) config/trading_config.yaml: now tracked (operator-vote: commit policy artifact)." ^
           -m "   Carries the R12 min_ml_confidence 0.70 -> 0.58 lowering applied 2026-04-30 after" ^
           -m "   1-trade-in-6-weeks audit. Floor 0.50 in _effective_min_conf preserved." ^
           -m "2) tools/optimize_per_pair.py: import gc, drop all_results from kept summary," ^
           -m "   del df, gc.collect every 9 configs in inner loop. Prior run OOM'd at symbol 1/19." ^
           -m "3) tools/run_walkforward_lab.cmd: call tools\restore_junction.cmd before python.exe." ^
           -m "   Prevents 'No module named ai_trading_agents.multi_agent' when pre-commit broke" ^
           -m "   the junction between scheduled runs (seen 2026-04-30 0230 vs 04-29 0427)." ^
           -m "4) tools/run_ea_parity_nightly.cmd: same junction-restore preflight, prophylactic." ^
           -m "" ^
           -m "Tests: ast.parse on optimize_per_pair OK; cmd files syntactically reviewed." ^
           -m "Postmortem context: docs/POSTMORTEMS/2026-04-30_min_conf_lowering_R12.md"
if errorlevel 1 (
    echo [!] first commit attempt failed - likely pre-commit reformatted files
    echo [!] re-staging and retrying once
    git add config\trading_config.yaml ^
            tools\optimize_per_pair.py ^
            tools\run_walkforward_lab.cmd ^
            tools\run_ea_parity_nightly.cmd
    git commit -m "ops: R12 follow-up fixes - per-pair OOM, schtasks junction guard, yaml under git" ^
               -m "(retry after pre-commit reformat; see commit_r12_fixes.cmd for details)"
    if errorlevel 1 (
        echo [X] second commit attempt failed - manual recovery needed
        exit /b 4
    )
)

echo.
echo === HEAD ===
git log -1 --format="%%h %%s"
echo.
echo [OK] R12 fixes committed.
