' Hidden launcher for brain liveness watchpet.
' Runs every 5 min via Windows Task Scheduler.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
WshShell.Run """C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\pythonw.exe"" tools\watchpet_brain_alive.py", 0, False
