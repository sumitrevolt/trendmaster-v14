@echo off
REM Delete stale MT5 signal JSON files that executor is skipping repeatedly.
REM These accumulated because TV webhooks wrote signals but executor rejected
REM them (concentration caps, news blackout, etc.) without cleanup. Now the
REM executor is spamming "skip ... stale signal" every 5 sec.
echo === Cleanup stale signals ===
set MT5DIR=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files

cd /d "%~dp0\.."

REM Find signal files older than 5 minutes and delete them.
echo Listing stale files...
forfiles /P "%MT5DIR%" /M trendmaster_signals*.json /D -1 /C "cmd /c if @isdir==FALSE echo @path" 2>nul
echo.
echo Deleting (5+ min old)...
forfiles /P "%MT5DIR%" /M trendmaster_signals*.json /D -1 /C "cmd /c if @isdir==FALSE del /Q @path" 2>nul

echo.
echo === Remaining signal files ===
dir /B "%MT5DIR%\trendmaster_signals*.json" 2>nul
echo.
echo Done.
timeout /t 3 /nobreak > nul
