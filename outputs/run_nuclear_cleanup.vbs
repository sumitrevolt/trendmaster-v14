Set shell = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
shell.CurrentDirectory = ROOT
shell.Run """" & ROOT & "\.venv\Scripts\python.exe"" """ & ROOT & "\outputs\nuclear_cleanup.py""", 0, True
