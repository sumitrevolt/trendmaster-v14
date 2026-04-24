@echo off
set EDIT="C:\Program Files\MetaTrader 5\MetaEditor64.exe"
set MQL=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5

echo [1] Compiling Indicators\TrendMaster_v14_Signals.mq5 ...
%EDIT% /compile:"%MQL%\Indicators\TrendMaster_v14_Signals.mq5" /log:"%MQL%\Indicators\compile.log"
echo    exit=%ERRORLEVEL%
type "%MQL%\Indicators\compile.log" 2>nul | findstr /i "error warning result"
if exist "%MQL%\Indicators\TrendMaster_v14_Signals.ex5" (
    echo    [OK] .ex5 produced
) else (
    echo    [X] no .ex5
)

echo.
echo [2] Compiling Scripts\ReApply_TrendMaster_v14.mq5 ...
%EDIT% /compile:"%MQL%\Scripts\ReApply_TrendMaster_v14.mq5" /log:"%MQL%\Scripts\compile_reapply.log"
echo    exit=%ERRORLEVEL%
type "%MQL%\Scripts\compile_reapply.log" 2>nul | findstr /i "error warning result"
if exist "%MQL%\Scripts\ReApply_TrendMaster_v14.ex5" (
    echo    [OK] .ex5 produced
) else (
    echo    [X] no .ex5
)
