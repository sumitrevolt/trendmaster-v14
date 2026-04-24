@echo off
REM =======================================================================
REM  tools\crg_hook.cmd
REM  Thin wrapper for the code-review-graph PostToolUse hook.
REM
REM  Behavior:
REM    - If the repo has a .git directory -> run incremental update
REM      (fast, typically <1s).
REM    - Otherwise -> exit 0 silently. `code-review-graph update` requires
REM      git for diffing and would otherwise error on every Edit/Write/Bash.
REM
REM  Why a wrapper: Claude Code's PostToolUse hook accepts a single
REM  command string and surfaces non-zero exits as errors, so calling
REM  `update` directly in a non-git workspace was failing on every tool
REM  use. This wrapper keeps the auto-update behavior for the moment the
REM  user runs `git init`, while staying silent today.
REM
REM  Manual full rebuild (incl. flows + communities): rebuild_graph.cmd
REM =======================================================================
setlocal
pushd "%~dp0\.."

if not exist ".git" (
    REM No git -> nothing to incrementally diff. Silently succeed.
    popd
    exit /b 0
)

where code-review-graph >nul 2>nul
if errorlevel 1 (
    REM CLI not on PATH. Don't fail the hook — just skip.
    popd
    exit /b 0
)

code-review-graph update --skip-flows >nul 2>nul
REM Never propagate failures out of the hook — a broken graph update must
REM not block an Edit/Write/Bash tool use. Exit 0 regardless.
popd
exit /b 0
