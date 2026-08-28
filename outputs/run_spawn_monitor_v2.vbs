Set shell = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
shell.CurrentDirectory = ROOT
shell.Run """" & ROOT & "\.venv\Scripts\pythonw.exe"" """ & ROOT & "\outputs\process_spawn_monitor_v2.py""", 0, True
