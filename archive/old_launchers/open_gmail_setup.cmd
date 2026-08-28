@echo off
REM ───────────────────────────────────────────────────────────────────
REM   One-click helper for TV email setup — opens both:
REM     1. Chrome at Google Account Security (App Password page)
REM     2. Notepad with config\.env file
REM   Created 2026-05-01 by Claude
REM ───────────────────────────────────────────────────────────────────

REM Open Google Account Security in Chrome
start "" "https://myaccount.google.com/security"

REM Wait 1 second so Chrome takes focus first
ping 127.0.0.1 -n 2 >nul

REM Open .env in Notepad (file path with spaces — wrap in quotes)
start "" notepad "C:\Users\Ratanshila\Documents\autmated trading\config\.env"

exit /b 0
