@echo off
REM Debug version — pauses at each step + logs all output
REM Created 2026-05-01 to diagnose why start_tv_email.cmd silently exits

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Open a log file we can read from the start
echo === debug run started === > logs\tv_email_debug.log
echo Working dir: %CD% >> logs\tv_email_debug.log
echo. >> logs\tv_email_debug.log

echo [1/4] env-vars check... >> logs\tv_email_debug.log
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os; print('USER=', os.getenv('TV_EMAIL_USER','MISSING')); print('PASS_LEN=', len(os.getenv('TV_EMAIL_APP_PASSWORD',''))); print('HOST=', os.getenv('TV_EMAIL_IMAP_HOST','imap.gmail.com')); print('PORT=', os.getenv('TV_EMAIL_IMAP_PORT','993'))" 1>> logs\tv_email_debug.log 2>&1
echo. >> logs\tv_email_debug.log

echo [2/4] tv_email_receiver import test... >> logs\tv_email_debug.log
.venv\Scripts\python.exe -c "import ai_trading_agents.tv_email_receiver; print('IMPORT OK')" 1>> logs\tv_email_debug.log 2>&1
echo. >> logs\tv_email_debug.log

echo [3/4] IMAP login test... >> logs\tv_email_debug.log
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os, imaplib; M=imaplib.IMAP4_SSL(os.getenv('TV_EMAIL_IMAP_HOST','imap.gmail.com'), int(os.getenv('TV_EMAIL_IMAP_PORT','993'))); M.login(os.getenv('TV_EMAIL_USER',''), os.getenv('TV_EMAIL_APP_PASSWORD','')); typ, data = M.select('INBOX'); print('IMAP OK count=', data); M.logout()" 1>> logs\tv_email_debug.log 2>&1
echo. >> logs\tv_email_debug.log

echo [4/4] starting poller in FOREGROUND... >> logs\tv_email_debug.log
.venv\Scripts\python.exe -u -m ai_trading_agents.tv_email_receiver 1>> logs\tv_email_debug.log 2>&1
echo. >> logs\tv_email_debug.log

echo === debug run done === >> logs\tv_email_debug.log
pause
