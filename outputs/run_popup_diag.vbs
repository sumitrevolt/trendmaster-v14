' Silently run popup diagnostic
Set shell = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
shell.CurrentDirectory = ROOT
shell.Run """" & ROOT & "\.venv\Scripts\python.exe"" """ & ROOT & "\outputs\find_popup_culprit.py""", 0, True
