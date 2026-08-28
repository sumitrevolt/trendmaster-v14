@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Run refresh once now ===
.venv\Scripts\python.exe tools\refresh_news_calendar.py
echo.

echo === Install weekly task (Mon 06:00 IST) ===
schtasks /Create ^
    /TN "TrendMaster News Calendar Refresh" ^
    /TR "wscript.exe \"C:\Users\Ratanshila\Documents\autmated trading\tools\refresh_news_calendar.vbs\"" ^
    /SC WEEKLY /D MON /ST 06:00 ^
    /F
echo.
schtasks /Query /TN "TrendMaster News Calendar Refresh" /FO LIST
