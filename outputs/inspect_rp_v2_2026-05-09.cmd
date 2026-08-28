@echo off
REM Run the v2 expanded Rocket Prime inspection.
setlocal
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo.
echo === Running v2 expanded inspection of Rocket Prime alert conditions ===
echo  Headed Chrome will open. Don't close it manually until script finishes.
echo  Report saved to docs\guides\rocket_prime_v2_report.txt
echo.
.venv\Scripts\python.exe tools\tv_alert_setup\inspect_rp_v2_expanded.py
echo.
echo === Output files ===
dir /B "docs\guides\rocket_prime_v2_*"
echo.
pause
endlocal
