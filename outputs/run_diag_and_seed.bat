@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo.
echo ############################################################
echo #  (A)  FOREX / COMMODITIES silence diagnostic
echo ############################################################
.venv\Scripts\python.exe outputs\diagnose_silent_teams.py
echo.
echo ############################################################
echo #  (B)  ea_parity nightly first run (seeds baseline)
echo ############################################################
.venv\Scripts\python.exe tools\ea_parity_nightly.py
