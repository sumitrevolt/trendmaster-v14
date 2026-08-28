@echo off
REM End-to-end cTrader setup. Operator clicks Authorize ONCE in browser.
REM Tokens, account_id, executor — all auto-handled by setup_ctrader_full.py.

cd /d "%~dp0\.."

echo === cTrader full setup — operator clicks Authorize once ===
echo.
echo  PRE-CHECK  redirect URI in cTrader app must be EXACTLY:
echo    http://127.0.0.1:8766/ctrader-oauth/callback
echo.

"%~dp0\..\.venv\Scripts\python.exe" "%~dp0\setup_ctrader_full.py"
echo.
pause
