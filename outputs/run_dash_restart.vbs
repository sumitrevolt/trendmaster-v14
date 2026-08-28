Set sh = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
sh.CurrentDirectory = ROOT
sh.Run """" & ROOT & "\.venv\Scripts\python.exe"" """ & ROOT & "\outputs\check_and_restart_dashboard.py""", 0, True
