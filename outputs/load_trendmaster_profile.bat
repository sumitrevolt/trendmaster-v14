@echo off
REM =======================================================================
REM  load_trendmaster_profile.bat
REM
REM  Kills the running MT5 terminal and restarts it with the
REM  TrendMaster_v14_All19 profile preselected via command-line.
REM  Result: 18 charts open, each with AI_SUPERBB_v14_TrendMaster EA
REM  attached. Brain's signal files get read, trades start on next tick.
REM
REM  Run this script yourself (I can't — MT5 is "read-only" tier for
REM  AI agents by system safety design, which is correct for a trading
REM  terminal). Double-click the .bat or run from PowerShell.
REM
REM  Safe to run any time. If MT5 was mid-fill, the broker doesn't
REM  cancel your positions - they remain on the server side and will
REM  be visible again as soon as MT5 re-logs in.
REM =======================================================================
setlocal
set "MT5=C:\Program Files\MetaTrader 5\terminal64.exe"
set "PROFILE=TrendMaster_v14_All19"

if not exist "%MT5%" (
    echo [load_profile] ERROR: MT5 not at %MT5%
    echo                Adjust the MT5 path in this .bat if it is installed elsewhere.
    pause
    exit /b 1
)

echo [load_profile] Stopping current MT5 terminal...
taskkill /IM terminal64.exe /F >nul 2>nul
timeout /t 3 /nobreak >nul

echo [load_profile] Starting MT5 with profile "%PROFILE%"...
start "" "%MT5%" /profile:"%PROFILE%"
timeout /t 6 /nobreak >nul

echo [load_profile] Verifying autotrading + profile via Python...
pushd "%~dp0\.."
python -c "import MetaTrader5 as mt5; mt5.initialize(); t=mt5.terminal_info(); print('trade_allowed=', bool(t.trade_allowed), ' path=', t.path); mt5.shutdown()" 2>nul
popd

echo.
echo [load_profile] Done. If trade_allowed is True and 18 chart tabs are
echo                visible at the bottom of MT5, the EA will start
echo                placing orders on the next Python brain tick.
echo.
echo                If autotrading is OFF: press Ctrl+E inside MT5 once
echo                to toggle it ON. Green circle in toolbar = enabled.
echo.
pause
