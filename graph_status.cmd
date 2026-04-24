@echo off
REM =======================================================================
REM  graph_status.cmd  -  Quick status + counts for the code-review-graph DB
REM
REM  Prints:
REM    - CLI status (if code-review-graph is on PATH)
REM    - schema / last-build metadata from graph.db
REM    - node/edge/flow counts + archive share
REM  Safe to run any time.
REM =======================================================================
setlocal
pushd "%~dp0"

if not exist ".code-review-graph\graph.db" (
    echo [graph_status] No graph DB found at .code-review-graph\graph.db
    echo                Run rebuild_graph.cmd to create it.
    popd
    exit /b 1
)

where code-review-graph >nul 2>nul
if not errorlevel 1 (
    code-review-graph status
    echo.
)

REM Detailed counts via tools\graph_status.py (uses only the stdlib).
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "tools\graph_status.py"
set "RC=%ERRORLEVEL%"

popd
endlocal & exit /b %RC%
