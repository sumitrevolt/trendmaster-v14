Set sh = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
sh.CurrentDirectory = ROOT
sh.Run """" & ROOT & "\.venv\Scripts\pythonw.exe"" """ & ROOT & "\tools\telegram_direction_listener.py""", 0, False
