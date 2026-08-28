@echo off
echo Deleting stale BTC signal file...
set TARGET=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals_BTCUSD.json
if exist "%TARGET%" (
    del /F /Q "%TARGET%"
    if errorlevel 1 (
        echo [X] delete failed
    ) else (
        echo [OK] deleted: %TARGET%
    )
) else (
    echo [INFO] file already gone: %TARGET%
)
echo.
echo === executor will stop logging stale-skip after next 5sec poll ===
timeout /t 10 /nobreak > nul
