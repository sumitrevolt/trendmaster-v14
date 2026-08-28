@echo off
REM ============================================================================
REM   inspect_rocket_prime_2026-05-09.cmd
REM
REM   Auto-discovers what alert conditions Rocket Prime exposes in TV UI by
REM   driving a Playwright headed browser. Output written to:
REM     docs/guides/rocket_prime_alert_conditions.txt
REM     docs/guides/rocket_prime_alert_dialog.png  (screenshot)
REM
REM   If TV cookies are expired, browser will pop up — you sign in within 8 min,
REM   script auto-resumes.
REM ============================================================================
setlocal
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo.
echo === Inspecting Rocket Prime alert conditions ===
echo  This will open a headed Chrome window via Playwright.
echo  If you need to sign in to TV, do it within 8 min.
echo.

.venv\Scripts\python.exe tools\tv_alert_setup\inspect_rocket_prime_conditions.py

echo.
echo === Output files ===
if exist "docs\guides\rocket_prime_alert_conditions.txt" (
    echo  [OK] docs\guides\rocket_prime_alert_conditions.txt
)
if exist "docs\guides\rocket_prime_alert_dialog.png" (
    echo  [OK] docs\guides\rocket_prime_alert_dialog.png
)
echo.
pause
endlocal
