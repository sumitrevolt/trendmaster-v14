' Hidden launcher for daily maintenance (log rotate + backup).
' Runs at 23:50 IST via Windows Task Scheduler.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
WshShell.Run """C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\python.exe"" tools\daily_maintenance.py >> logs\daily_maintenance.log 2>&1", 0, False
