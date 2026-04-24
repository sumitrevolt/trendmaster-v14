@echo off
REM =======================================================================
REM  rebuild_graph.cmd  -  Full rebuild of the code-review-graph DB
REM
REM  The PostToolUse hook in .claude\settings.json runs
REM    code-review-graph update --skip-flows
REM  on every Edit/Write/Bash, so structural data stays fresh but FLOWS are
REM  not recomputed on-the-fly. Run this script after a significant refactor
REM  or before running flow-dependent queries (get_affected_flows, etc.) to
REM  force a full rebuild including flows + community post-processing.
REM =======================================================================
setlocal
pushd "%~dp0"

echo.
echo [rebuild_graph] Starting full rebuild at %DATE% %TIME%
echo [rebuild_graph] Project: %CD%
echo.

where code-review-graph >nul 2>nul
if errorlevel 1 (
    echo [rebuild_graph] ERROR: code-review-graph CLI not on PATH.
    echo                Install it or activate the venv that has it, then re-run.
    popd
    exit /b 1
)

code-review-graph update
if errorlevel 1 (
    echo [rebuild_graph] ERROR: update failed with exit code %ERRORLEVEL%
    popd
    exit /b %ERRORLEVEL%
)

echo.
echo [rebuild_graph] Rebuild complete.  Current status:
echo.
code-review-graph status

popd
endlocal
