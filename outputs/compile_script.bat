@echo off
set MQLROOT=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5
set SCRIPT=%MQLROOT%\Scripts\AutoAttach_TrendMaster_v14.mq5
set LOG=%MQLROOT%\Scripts\AutoAttach_TrendMaster_v14.log

echo [i] Compiling %SCRIPT%
"C:\Program Files\MetaTrader 5\MetaEditor64.exe" /compile:"%SCRIPT%" /log:"%LOG%"
echo [i] Exit code: %ERRORLEVEL%

echo.
echo === Compile log ===
if exist "%LOG%" (
    type "%LOG%"
) else (
    echo (no log written)
)

echo.
echo === Checking for .ex5 ===
if exist "%MQLROOT%\Scripts\AutoAttach_TrendMaster_v14.ex5" (
    dir "%MQLROOT%\Scripts\AutoAttach_TrendMaster_v14.ex5"
    echo [OK] Compiled .ex5 produced
) else (
    echo [X] No .ex5 produced
)
