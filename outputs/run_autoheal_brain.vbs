Set sh = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
sh.CurrentDirectory = ROOT
sh.Run """" & ROOT & "\.venv\Scripts\pythonw.exe"" """ & ROOT & "\outputs\enable_autoheal_and_brain.py""", 0, True
