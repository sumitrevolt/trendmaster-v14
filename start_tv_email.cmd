@echo off
REM ───────────────────────────────────────────────────────────────────────────
REM   TradingView email IMAP poller launcher  (BACKUP path for webhook mode)
REM
REM   Use this when the webhook + tunnel are unavailable (TV plan downgrade,
REM   tunnel outage, network issues). Polls Gmail for TV alert emails and
REM   dispatches them through the same write_tv_signal() pipeline as the
REM   webhook. Latency: ~10-20s end-to-end (TV email send + IMAP poll).
REM
REM   Restored to repo root 2026-05-04 from archive\old_launchers\.
REM   Logs: logs\tv_email.log + logs\tv_email.err
REM ───────────────────────────────────────────────────────────────────────────

cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Pre-flight 1: TV_EMAIL.enabled flag must be True in config\settings.py
.venv\Scripts\python.exe -c "import sys; from config import settings as s; sys.exit(0 if (s.TV_EMAIL or {}).get('enabled', False) else 2)" >nul 2>&1
if errorlevel 2 (
    echo [X] PRE-FLIGHT FAIL: TV_EMAIL.enabled is False in config\settings.py
    echo     Edit config\settings.py and flip TV_EMAIL["enabled"] = True
    exit /b 2
)

REM Pre-flight 2: TV_EMAIL_USER + TV_EMAIL_APP_PASSWORD must be set in config\.env
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os, sys; sys.exit(0 if os.getenv('TV_EMAIL_USER','').strip() and os.getenv('TV_EMAIL_APP_PASSWORD','').strip() else 2)"
if errorlevel 2 (
    echo [X] PRE-FLIGHT FAIL: TV_EMAIL_USER or TV_EMAIL_APP_PASSWORD missing in config\.env
    echo     Generate Gmail App Password:
    echo         myaccount.google.com ^> Security ^> 2-Step Verification ^> App passwords
    echo     Then add to config\.env:
    echo         TV_EMAIL_USER=you@gmail.com
    echo         TV_EMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx     (16 chars, no spaces)
    exit /b 3
)

REM Pre-flight 3: tv_email_receiver imports cleanly
.venv\Scripts\python.exe -c "import ai_trading_agents.tv_email_receiver" >nul 2>&1
if errorlevel 1 (
    echo [X] PRE-FLIGHT FAIL: ai_trading_agents.tv_email_receiver failed to import.
    exit /b 4
)

REM Pre-flight 4: IMAP login works (catches wrong creds before background detach)
.venv\Scripts\python.exe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('config/.env')); import os, imaplib, sys; M=imaplib.IMAP4_SSL(os.getenv('TV_EMAIL_IMAP_HOST','imap.gmail.com'), int(os.getenv('TV_EMAIL_IMAP_PORT','993'))); M.login(os.getenv('TV_EMAIL_USER',''), os.getenv('TV_EMAIL_APP_PASSWORD','')); M.select('INBOX'); M.logout(); print('[OK] IMAP login + INBOX select succeeded')"
if errorlevel 1 (
    echo [X] PRE-FLIGHT FAIL: IMAP login failed.
    echo     Common causes:
    echo       - TV_EMAIL_APP_PASSWORD is your real Gmail password (won't work; use App Password)
    echo       - 2-Step Verification not enabled on Gmail (App passwords require it)
    echo       - "Less secure apps" still on (Google retired this; use App Password)
    exit /b 5
)

REM Kill any prior poller
echo === killing any prior tv_email process ===
for /f "tokens=2" %%a in ('tasklist /v /fi "imagename eq python.exe" ^| findstr /i "TV_Email"') do taskkill /F /PID %%a 2>nul

REM Truncate log files for a clean run
echo === truncating tv_email logs ===
type nul > logs\tv_email.log
type nul > logs\tv_email.err

echo === starting TV email poller detached ===
start "TV_Email - LIVE" /MIN cmd /c "title TV_Email - LIVE && cd /d C:\Users\Ratanshila\Documents\autmated trading && .venv\Scripts\python.exe -u -m ai_trading_agents.tv_email_receiver 1>> logs\tv_email.log 2>> logs\tv_email.err"

echo === wait 5s for boot ===
ping 127.0.0.1 -n 6 >nul

REM Boot crash check
.venv\Scripts\python.exe -c "import sys, pathlib; p = pathlib.Path(r'logs\tv_email.err'); txt = p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''; sys.exit(2 if 'Traceback' in txt else 0)"
if errorlevel 2 (
    echo [X] BOOT CRASH: logs\tv_email.err contains a Traceback.
    powershell -NoProfile -Command "Get-Content -Path 'logs\tv_email.err' -Tail 25"
    exit /b 6
)

echo.
echo === DONE — email poller live ===
echo   In TradingView: Create Alert ^> Notifications ^> enable "Send email" only.
echo   Each TV alert email auto-routed through tv_executor on next IMAP poll.
echo   Tail activity:  powershell -Command "Get-Content -Path 'logs\tv_email.log' -Wait -Tail 20"
