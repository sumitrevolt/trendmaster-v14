Set shell = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
shell.CurrentDirectory = ROOT
shell.Run """" & ROOT & "\.venv\Scripts\pythonw.exe"" """ & ROOT & "\outputs\patch_all_vbs.py""", 0, True
