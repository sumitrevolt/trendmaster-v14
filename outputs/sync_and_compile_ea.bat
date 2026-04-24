@echo off
set REPO_EA=C:\Users\Ratanshila\Documents\autmated trading\AI_SUPERBB_v14_TrendMaster.mq5
set MT5_EA=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\AI_SUPERBB_v14_TrendMaster.mq5
set EDIT="C:\Program Files\MetaTrader 5\MetaEditor64.exe"

echo [1] Copying updated EA source to MT5 Experts folder...
copy /Y "%REPO_EA%" "%MT5_EA%"
if errorlevel 1 (
    echo [X] Copy failed
    goto :end
)

echo.
echo [2] Compiling via MetaEditor...
%EDIT% /compile:"%MT5_EA%" /log:"%MT5_EA%.log"
echo    exit code = %ERRORLEVEL%

echo.
echo === Compile log ===
if exist "%MT5_EA%.log" (
    type "%MT5_EA%.log" | findstr /i "error warning result information"
)

echo.
echo === Checking for .ex5 ===
set EX5=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\AI_SUPERBB_v14_TrendMaster.ex5
if exist "%EX5%" (
    dir "%EX5%" | findstr /i "SUPERBB"
    echo [OK] EA compiled — MT5 will auto-reload running instances
) else (
    echo [X] No .ex5 produced
)

:end
