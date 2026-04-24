@echo off
REM =======================================================================
REM  tools\install_git_hooks.cmd
REM
REM  Installs the pre-commit hook that runs the code-review-graph
REM  incremental update before each commit. Safe to re-run — the hook
REM  file is rewritten each time.
REM
REM  Why: the PostToolUse hook only fires inside Claude Code sessions.
REM  Editing with another tool (VS Code, notepad, PyCharm) leaves the
REM  graph stale until the next Claude Code session or manual rebuild.
REM  The pre-commit hook closes that gap at commit time.
REM =======================================================================
setlocal
pushd "%~dp0\.."

if not exist ".git" (
    echo [install_git_hooks] No .git directory found; run `git init` first.
    popd
    exit /b 1
)

set "HOOK=.git\hooks\pre-commit"

(
    echo #!/bin/sh
    echo # Auto-installed by tools/install_git_hooks.cmd
    echo # Runs code-review-graph incremental update on commit so the
    echo # graph DB always reflects the state being committed.
    echo.
    echo if command -v code-review-graph ^>/dev/null 2^>^&1; then
    echo     code-review-graph update --skip-flows ^>/dev/null 2^>^&1 ^|^| true
    echo fi
    echo exit 0
) > "%HOOK%"

echo [install_git_hooks] Installed %HOOK%
echo.
echo The hook will now run `code-review-graph update --skip-flows`
echo before every commit. Failures are non-blocking (commit proceeds
echo regardless, so a broken CLI never blocks your work).

popd
endlocal
