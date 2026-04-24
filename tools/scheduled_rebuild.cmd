@echo off
REM =======================================================================
REM  tools\scheduled_rebuild.cmd
REM
REM  Full code-review-graph rebuild, intended to run daily via Windows
REM  Task Scheduler. Refreshes flows, communities, FTS, and risk index
REM  (things the `--skip-flows` PostToolUse/pre-commit hooks skip for
REM  speed).
REM
REM  Install the scheduled task:
REM    tools\install_scheduled_rebuild.cmd
REM
REM  Manual run:
REM    rebuild_graph.cmd   (interactive, prints status)
REM    tools\scheduled_rebuild.cmd   (quiet, logs to file)
REM =======================================================================
setlocal
pushd "%~dp0\.."

set "LOGDIR=logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\code_review_graph_rebuild.log"

echo. >> "%LOG%"
echo === Scheduled rebuild at %DATE% %TIME% === >> "%LOG%"

where code-review-graph >nul 2>nul
if errorlevel 1 (
    echo [scheduled_rebuild] CLI not on PATH, skipping. >> "%LOG%"
    popd
    exit /b 0
)

code-review-graph build >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo [scheduled_rebuild] exit=%RC% >> "%LOG%"

popd
endlocal & exit /b %RC%
