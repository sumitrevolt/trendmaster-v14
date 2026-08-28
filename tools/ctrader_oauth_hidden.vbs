' Hidden launcher for ctrader_oauth.py (waits 5 min for redirect)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
WshShell.Run """C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\python.exe"" tools\ctrader_oauth.py >> logs\ctrader_oauth.log 2>&1", 0, False
