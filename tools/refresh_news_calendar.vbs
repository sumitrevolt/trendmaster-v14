' Hidden launcher for weekly news calendar refresh.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
WshShell.Run """C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\python.exe"" tools\refresh_news_calendar.py >> logs\refresh_news_calendar.log 2>&1", 0, False
