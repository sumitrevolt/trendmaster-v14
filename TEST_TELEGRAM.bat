@echo off
REM ====================================================================
REM  TEST_TELEGRAM.bat — sanity check for Telegram alerts
REM  Sends one canned message to the chat configured in
REM    config\.env  or  ai_trading_agents\.env
REM  If the message lands on Sumit's phone, the pipeline is wired up.
REM ====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ======================================================================
echo   TrendMaster v14 - Telegram smoke test
echo ======================================================================
echo.

REM ---- Activate project venv if present ------------------------------
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [X] 'python' not found on PATH. Install Python 3.10+.
    goto :fail
)

REM ---- Make sure `requests` is installed ------------------------------
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo [i] Installing 'requests' for Telegram HTTP ...
    python -m pip install --quiet requests
    if errorlevel 1 (
        echo [X] pip install requests failed. Check network.
        goto :fail
    )
)

REM ---- python-dotenv is optional but nice ----------------------------
python -c "import dotenv" >nul 2>&1
if errorlevel 1 (
    python -m pip install --quiet python-dotenv >nul 2>&1
)

echo [i] Sending test message ...
echo.
python -m ai_trading_agents.telegram_notifier test
set RC=%errorlevel%
echo.
if "%RC%"=="0" (
    echo ======================================================================
    echo   [OK] Test message dispatched.
    echo   Apne Telegram me check karo - "TrendMaster v14 connectivity test"
    echo   naam ka message aana chahiye.
    echo ======================================================================
) else (
    echo ======================================================================
    echo   [X] Test failed. Check above for the reason.
    echo   Common fixes:
    echo     - config\.env me TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED=true set karo
    echo     - Internet check karo (Telegram API reachable hona chahiye)
    echo     - Bot token Telegram BotFather se freshly verify karo
    echo ======================================================================
)
echo.
pause >nul
endlocal
exit /b %RC%

:fail
echo.
echo ==================== TELEGRAM TEST SETUP FAILED ====================
pause >nul
endlocal
exit /b 1
