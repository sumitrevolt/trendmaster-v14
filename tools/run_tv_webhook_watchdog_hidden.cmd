@echo off
REM Hidden wrapper — uses pythonw.exe (NO console window) so the schtask
REM doesn't pop a terminal every 5 minutes.
REM Even though this .cmd is invoked, calling pythonw.exe means no Python window.
REM The brief flash of the cmd shell is unavoidable when invoked via cmd /c,
REM but pythonw.exe eliminates the much-longer-lived Python window.
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\pythonw.exe tools\tv_webhook_watchdog.py >> logs\tv_webhook_watchdog.log 2>&1
