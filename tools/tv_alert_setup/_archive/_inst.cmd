@echo off
setlocal
set "ROOT=C:\Users\Ratanshila\Documents\autmated trading"
cd /d "%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" "%ROOT%\tools\tv_alert_setup\run_instant_freq_atomic.py" > "%ROOT%\logs\set_freq.out" 2>&1
echo EXIT %ERRORLEVEL% >> "%ROOT%\logs\set_freq.out"
