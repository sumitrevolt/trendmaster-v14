Set shell = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
shell.CurrentDirectory = ROOT
shell.Run """" & ROOT & "\.venv\Scripts\pythonw.exe"" """ & ROOT & "\outputs\disable_noisy_schtasks.py""", 0, True
