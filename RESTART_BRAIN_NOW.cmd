@echo off
REM ===========================================================================
REM RESTART BRAIN -- 2026-05-06
REM Brain has been DEAD since 2026-05-05 04:48. Restart via canonical script.
REM ===========================================================================
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Restarting brain via start_brain_clean.cmd ===
echo.
call start_brain_clean.cmd
echo.
echo === Wait 15s for brain to settle, then verify ===
ping 127.0.0.1 -n 16 >nul
echo.
echo === Diagnose ===
.venv\Scripts\python.exe tools\diagnose_zero_trades.py
echo.
echo === Brain process check ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}} | Format-Table"
echo.
pause
